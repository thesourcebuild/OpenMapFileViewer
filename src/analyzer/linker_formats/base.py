from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from ..models import MemoryRegion
from ..utils import region_kind



class LinkerFormatParser(Protocol):
    FORMAT_NAME: str
    SUFFIXES: tuple[str, ...]

    def can_parse(text: str) -> bool:
        ...

    def parse(lines: Sequence[str]) -> list[MemoryRegion]:
        ...


_PARSERS: tuple[LinkerFormatParser, ...] = ()


def set_parsers(parsers: Sequence[LinkerFormatParser]) -> None:
    global _PARSERS
    _PARSERS = tuple(parsers)


def _get_parser_for_suffix(suffix: str) -> LinkerFormatParser | None:
    suffix = suffix.lower()
    for parser in _PARSERS:
        if suffix in parser.SUFFIXES:
            return parser
    return None


def get_parser_for_path(path: Path) -> LinkerFormatParser | None:
    return _get_parser_for_suffix(path.suffix)


def detect_linker_parser(text: str) -> LinkerFormatParser | None:
    for parser in _PARSERS:
        if parser.can_parse(text):
            return parser
    return None


def detect_linker_format(text: str) -> str:
    parser = detect_linker_parser(text)
    return parser.FORMAT_NAME if parser is not None else "generic"


def filter_contained_regions(regions: Sequence[MemoryRegion]) -> list[MemoryRegion]:
    ordered = sorted(enumerate(regions), key=lambda item: (-item[1].length, item[1].origin, item[0]))
    kept: list[tuple[int, MemoryRegion]] = []
    for index, region in ordered:
        if region.length <= 0:
            continue
        end = region.origin + region.length
        r_kind = region_kind(region.name, region.attrs, region.origin, region.length)
        if any(
            existing.origin <= region.origin
            and (existing.origin + existing.length) >= end
            and region_kind(existing.name, existing.attrs, existing.origin, existing.length) == r_kind
            for _, existing in kept
        ):
            continue
        kept.append((index, region))
    kept.sort(key=lambda item: (item[1].origin, item[0], item[1].name))
    return [region for _, region in kept]


def parse_linker_file(path: Path) -> tuple[str, list[MemoryRegion], dict]:
    text = path.read_text(errors="replace")
    parser = get_parser_for_path(path) or detect_linker_parser(text)
    if parser is None:
        return "generic", [], {}
    result = parser.parse(text.splitlines())
    # Support both old-style list return and new-style (regions, extras) tuple
    if isinstance(result, tuple):
        regions, extras = result
    else:
        regions, extras = result, {}
    return parser.FORMAT_NAME, filter_contained_regions(regions), extras
