"""Audit log and Settings data access."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Setting


class SystemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ----- Audit -----
    async def log(
        self,
        action: str,
        actor_id: Optional[int] = None,
        entity: Optional[str] = None,
        entity_id: Optional[int] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                detail=detail,
            )
        )
        await self.session.flush()

    # ----- Settings (key/value) -----
    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        setting = await self.session.get(Setting, key)
        return setting.value if setting and setting.value is not None else default

    async def set(self, key: str, value: str) -> None:
        stmt = (
            pg_insert(Setting)
            .values(key=key, value=value)
            .on_conflict_do_update(index_elements=["key"], set_={"value": value})
        )
        await self.session.execute(stmt)

    async def all(self) -> dict[str, Optional[str]]:
        res = await self.session.execute(select(Setting))
        return {s.key: s.value for s in res.scalars().all()}
