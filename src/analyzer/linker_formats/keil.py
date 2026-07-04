from __future__ import annotations

import re
from typing import Sequence

from ..models import MemoryRegion
from ..utils import parse_byte_size, parse_int
from .base import filter_contained_regions

FORMAT_NAME = "keil"
SUFFIXES = (".sct",)

REGION_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][\w.$]*)\s+(?P<base>\+?(?:0x[0-9A-Fa-f]+|\d+))\s+(?P<size>(?:0x[0-9A-Fa-f]+|\d+)(?:[KMGkmg](?:i?[Bb]?)?)?)\\b",
    re.I,
)

# Keil .sct ARM_LIB_STACK / ARM_LIB_HEAP have a size as their third token.
# They look like:  ARM_LIB_STACK 0x20007C00 EMPTY 0x400 { }
# Also common:     ARM_LIB_HEAP  0x20007C00 EMPTY 0x200 { }
_STACK_RE = re.compile(
    r"^\s*ARM_LIB_STACK\s+\S+\s+\S+\s+(?P<size>0x[0-9A-Fa-f]+|\d+)",
    re.I,
)
_HEAP_RE = re.compile(
    r"^\s*ARM_LIB_HEAP\s+\S+\s+\S+\s+(?P<size>0x[0-9A-Fa-f]+|\d+)",
    re.I,
)
# Also handle  __stack_size EQU 0x400  /  StackSize EQU 0x400  style
_EQU_STACK_RE = re.compile(
    r"^\s*(?:[A-Za-z_][\w.$]*stack[A-Za-z_]*|stack[A-Za-z_]*)\s+(?:EQU|=)\s+(?P<val>0x[0-9A-Fa-f]+|\d+)",
    re.I,
)
_EQU_HEAP_RE = re.compile(
    r"^\s*(?:[A-Za-z_][\w.$]*heap[A-Za-z_]*|heap[A-Za-z_]*)\s+(?:EQU|=)\s+(?P<val>0x[0-9A-Fa-f]+|\d+)",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "lr_" in sample or "scatter" in sample or "load region" in sample


def _parse_size(token: str) -> int:
    try:
        return parse_byte_size(token)
    except ValueError:
        return parse_int(token)


def parse(lines: Sequence[str]) -> tuple[list[MemoryRegion], dict[str, int]]:
    regions: list[MemoryRegion] = []
    extras: dict[str, int] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        # Stack / heap size detection
        m = _STACK_RE.match(line)
        if m:
            try:
                extras["stack_size"] = _parse_size(m.group("size"))
            except ValueError:
                pass

        m = _HEAP_RE.match(line)
        if m:
            try:
                extras["heap_size"] = _parse_size(m.group("size"))
            except ValueError:
                pass

        m = _EQU_STACK_RE.match(line)
        if m and "stack_size" not in extras:
            try:
                extras["stack_size"] = parse_int(m.group("val"))
            except ValueError:
                pass

        m = _EQU_HEAP_RE.match(line)
        if m and "heap_size" not in extras:
            try:
                extras["heap_size"] = parse_int(m.group("val"))
            except ValueError:
                pass

        match = REGION_RE.match(line)
        if not match:
            continue

        base_token = match.group("base")
        if base_token.startswith("+"):
            continue

        try:
            origin = parse_int(base_token)
            length = _parse_size(match.group("size"))
        except ValueError:
            continue

        if length <= 0:
            continue

        regions.append(
            MemoryRegion(
                name=match.group("name"),
                origin=origin,
                length=length,
                attrs="scatter",
            )
        )

    return filter_contained_regions(regions), extras
