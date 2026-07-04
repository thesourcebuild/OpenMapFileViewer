from __future__ import annotations

from . import gld, gnu, iar, keil
from .base import detect_linker_format, parse_linker_file, set_parsers

set_parsers((gnu, gld, keil, iar))

SUPPORTED_LINKER_FORMATS = ("auto", "gnu", "gld", "keil", "iar")

__all__ = [
    "SUPPORTED_LINKER_FORMATS",
    "detect_linker_format",
    "parse_linker_file",
]
