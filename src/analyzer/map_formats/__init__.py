from __future__ import annotations

from . import gnu, iar, keil, msvc, ti
from .base import FormatParser, format_matches

PARSERS: tuple[FormatParser, ...] = (gnu, keil, iar, ti, msvc)


def get_parser(format_name: str) -> FormatParser | None:
    for parser in PARSERS:
        if format_matches(parser, format_name):
            return parser
    return None
