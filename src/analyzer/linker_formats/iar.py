from __future__ import annotations

import re
from typing import Sequence

from ..models import MemoryRegion
from ..utils import parse_int
from .base import filter_contained_regions

FORMAT_NAME = "iar"
SUFFIXES = (".icf",)

REGION_DEF_RE = re.compile(
    r"^\s*define\s+region\s+(?P<name>[A-Za-z_][\w.$]*)\s*=\s*(.+)",
    re.I,
)

REGION_CHUNK_RE = re.compile(
    r"(?:(?P<space>[A-Za-z_][\w.$]*)\s*:\s*)?\[\s*from\s+(?P<start>[A-Za-z0-9_]+)\s+to\s+(?P<end>[A-Za-z0-9_]+)\s*\]",
    re.I,
)

SYMBOL_RE = re.compile(
    r"^\s*define\s+(?:exported\s+)?symbol\s+(?P<name>[A-Za-z_][\w.$]*)\s*=\s*(?P<val>0x[0-9A-Fa-f]+|\d+)\s*;?",
    re.I,
)

_STACK_KEYS = re.compile(r"size_cstack|size_stack|__stack_size", re.I)
_HEAP_KEYS  = re.compile(r"size_heap|__heap_size", re.I)

# --- Placement directive patterns (run on full text, multi-line) ---
# place at address mem:<sym_or_hex> { <items> };
_PLACE_AT_RE = re.compile(
    r"place\s+at\s+address\s+\w+:(?P<addr>[A-Za-z0-9_]+)\s*\{(?P<content>[^}]+)\}\s*;",
    re.I | re.DOTALL,
)
# place in <region> { <items> };
_PLACE_IN_RE = re.compile(
    r"place\s+in\s+(?P<region>[A-Za-z_]\w*)\s*\{(?P<content>[^}]+)\}\s*;",
    re.I | re.DOTALL,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "define region" in sample or "place in" in sample or "iar" in sample


def _parse_content_items(content_str: str) -> list[dict]:
    """
    Parse comma-separated items from a 'place in/at' content block.
    Returns list of {label, kind} dicts.
    kind: 'section' | 'qualifier' | 'block'
    """
    items = []
    for part in re.split(r",\s*", content_str.strip()):
        part = part.strip()
        if not part:
            continue
        # block CSTACK / block HEAP
        m = re.match(r"block\s+(?P<name>\w+)", part, re.I)
        if m:
            items.append({"label": m.group("name"), "kind": "block"})
            continue
        # [readonly|readwrite] section .name
        m = re.match(r"(?:(?:readonly|readwrite)\s+)?section\s+(?P<name>\S+)", part, re.I)
        if m:
            items.append({"label": m.group("name"), "kind": "section"})
            continue
        # bare qualifier: readonly / readwrite
        m = re.match(r"(?P<q>readonly|readwrite)\b", part, re.I)
        if m:
            items.append({"label": m.group("q").lower(), "kind": "qualifier"})
            continue
    return items


def _parse_placements(text: str, symbols: dict[str, int]) -> list[dict]:
    """Parse all place-at-address and place-in directives from the ICF text."""
    placements: list[dict] = []

    # place at address
    for m in _PLACE_AT_RE.finditer(text):
        addr_token = m.group("addr")
        # Resolve symbol → int
        addr_val = symbols.get(addr_token)
        if addr_val is not None:
            region_label = f"0x{addr_val:08X}"
        else:
            try:
                region_label = f"0x{parse_int(addr_token):08X}"
            except ValueError:
                region_label = addr_token
        for item in _parse_content_items(m.group("content")):
            placements.append({**item, "region": region_label, "at_address": True})

    # place in region
    for m in _PLACE_IN_RE.finditer(text):
        region = m.group("region")
        for item in _parse_content_items(m.group("content")):
            placements.append({**item, "region": region, "at_address": False})

    return placements


def parse(lines: Sequence[str]) -> tuple[list[MemoryRegion], dict]:
    regions: list[MemoryRegion] = []
    symbols: dict[str, int] = {}
    extras: dict = {}

    for line in lines:
        sym_match = SYMBOL_RE.search(line)
        if sym_match:
            try:
                val = parse_int(sym_match.group("val"))
                sym_name = sym_match.group("name")
                symbols[sym_name] = val
                if _STACK_KEYS.search(sym_name):
                    extras["stack_size"] = val
                if _HEAP_KEYS.search(sym_name):
                    extras["heap_size"] = val
            except ValueError:
                pass
            continue

        def_match = REGION_DEF_RE.search(line)
        if not def_match:
            continue

        name = def_match.group("name")
        chunks = list(REGION_CHUNK_RE.finditer(def_match.group(2)))

        for i, match in enumerate(chunks):
            def resolve(val_str: str) -> int:
                if val_str in symbols:
                    return symbols[val_str]
                return parse_int(val_str)

            try:
                start = resolve(match.group("start"))
                end = resolve(match.group("end"))
            except ValueError:
                continue

            if end < start:
                continue

            region_name = name if len(chunks) == 1 or i == 0 else f"{name}_{i+1}"
            regions.append(
                MemoryRegion(
                    name=region_name,
                    origin=start,
                    length=end - start + 1,
                    attrs=match.group("space") or "mem",
                )
            )

    # Parse place-in / place-at directives from the full text
    full_text = "\n".join(lines)
    placements = _parse_placements(full_text, symbols)
    if placements:
        extras["placements"] = placements

    return filter_contained_regions(regions), extras
