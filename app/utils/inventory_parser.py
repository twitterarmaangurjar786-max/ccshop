"""Parse uploaded TXT/CSV stock files and compute category breakdown."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from app.utils.text import extract_category, is_valid_line, line_hash


@dataclass
class ParseResult:
    total_lines: int = 0
    invalid_lines: int = 0
    file_duplicates: int = 0
    db_duplicates: int = 0
    valid_lines: List[Tuple[str, str, str]] = field(default_factory=list)
    # category -> count
    categories: Dict[str, int] = field(default_factory=dict)

    @property
    def valid_count(self) -> int:
        return len(self.valid_lines)

    @property
    def duplicates(self) -> int:
        return self.file_duplicates + self.db_duplicates


def parse_lines(raw_text: str, existing_hashes: Set[str]) -> ParseResult:
    """Parse raw file text.

    ``valid_lines`` items are tuples of ``(line_data, category, content_hash)``.
    Duplicates inside the file and against ``existing_hashes`` (database) are removed.
    """
    result = ParseResult()
    seen_in_file: Set[str] = set()

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        result.total_lines += 1

        if not is_valid_line(line):
            result.invalid_lines += 1
            continue

        h = line_hash(line)
        if h in seen_in_file:
            result.file_duplicates += 1
            continue
        if h in existing_hashes:
            result.db_duplicates += 1
            continue

        seen_in_file.add(h)
        category = extract_category(line)
        assert category is not None
        result.valid_lines.append((line, category, h))
        result.categories[category] = result.categories.get(category, 0) + 1

    return result
