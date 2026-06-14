"""Stock upload: parse file, auto-generate categories, dedup, persist."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PreOrderStatus
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.marketing_repo import MarketingRepository
from app.repositories.system_repo import SystemRepository
from app.utils.inventory_parser import ParseResult, parse_lines


class UploadService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.inventory = InventoryRepository(session)
        self.marketing = MarketingRepository(session)
        self.system = SystemRepository(session)

    async def prepare_upload(self, raw_text: str) -> ParseResult:
        """Scan the file: count totals, remove in-file and DB duplicates,
        and build the auto-generated category breakdown.
        """
        # Phase 1: in-file dedup + validation (no DB hashes yet)
        first_pass = parse_lines(raw_text, existing_hashes=set())

        # Phase 2: detect duplicates already stored in the database
        candidate_hashes = [h for (_, _, h) in first_pass.valid_lines]
        db_hashes = await self.inventory.existing_hashes(candidate_hashes)

        if not db_hashes:
            return first_pass

        # Re-filter against DB duplicates
        result = ParseResult(
            total_lines=first_pass.total_lines,
            invalid_lines=first_pass.invalid_lines,
            file_duplicates=first_pass.file_duplicates,
        )
        for line_data, category, h in first_pass.valid_lines:
            if h in db_hashes:
                result.db_duplicates += 1
                continue
            result.valid_lines.append((line_data, category, h))
            result.categories[category] = result.categories.get(category, 0) + 1
        return result

    async def commit_upload(
        self, seller_id: int, parse_result: ParseResult, price: Decimal
    ) -> Dict[str, int]:
        """Persist parsed inventory. Returns a category -> inserted-count map."""
        grouped: Dict[str, list[dict]] = defaultdict(list)
        for line_data, category, content_hash in parse_result.valid_lines:
            grouped[category].append(
                {
                    "category": category,
                    "line_data": line_data,
                    "content_hash": content_hash,
                }
            )

        inserted: Dict[str, int] = {}
        notify_categories: list[str] = []
        for category, rows in grouped.items():
            offer = await self.inventory.get_or_create_offer(seller_id, category, price)
            # New offers (no sales yet) adopt the latest price.
            if offer.total_lines == 0:
                await self.inventory.set_price(offer.id, price)

            for r in rows:
                r["seller_inventory_id"] = offer.id
                r["seller_id"] = seller_id

            count = await self.inventory.bulk_insert_lines(rows)
            await self.inventory.increment_total(offer.id, count)
            inserted[category] = count
            notify_categories.append(category)

        await self.system.log(
            action="inventory_uploaded",
            actor_id=seller_id,
            entity="seller",
            entity_id=seller_id,
            detail={"categories": inserted, "price": str(price)},
        )
        # Return both data and pending preorder categories for the caller to notify.
        self._pending_notifications = notify_categories
        return inserted

    async def pending_preorders(self, category: str):
        return await self.marketing.waiting_preorders_for_category(category)
