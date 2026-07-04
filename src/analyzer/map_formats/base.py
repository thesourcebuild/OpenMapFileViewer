from __future__ import annotations

from typing import Protocol, Sequence

from ..models import Analysis


class FormatParser(Protocol):
    FORMAT_NAME: str
    ALIASES: tuple[str, ...]

    def can_parse(text: str) -> bool:
        ...

    def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
        ...


def append_hint(analysis: Analysis, hint: str) -> None:
    if hint not in analysis.format_hints:
        analysis.format_hints.append(hint)


def format_matches(parser: FormatParser, format_name: str) -> bool:
    normalized = (format_name or "").lower()
    return normalized == parser.FORMAT_NAME or normalized in parser.ALIASES
