from __future__ import annotations

import re
from typing import Sequence

from ..models import MemoryRegion
from ..utils import parse_byte_size, parse_int

FORMAT_NAME = "gnu"
SUFFIXES = (".ld", ".lds")

MEMORY_LINE_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][\w.$-]*)\s*(?:\((?P<attrs>[^)]*)\))?\s*:\s*(?P<body>.+)$",
    re.I,
)
TOKEN_RE = re.compile(r"(?i)\b(?P<key>ORIGIN|ORG|LENGTH|LEN)\s*=\s*(?P<value>[^,\s]+)")

# Stack/heap assignment patterns common in STM32 CubeMX ld scripts
_ASSIGN_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][\w.$]*)\s*=\s*(?P<val>0x[0-9A-Fa-f]+|\d+[KMGkmg]?[Ii]?[Bb]?|\d+)\s*;",
    re.I,
)
_STACK_KEYS = re.compile(r"stack.?size|min.?stack|stack.?min", re.I)
_HEAP_KEYS  = re.compile(r"heap.?size|min.?heap|heap.?min", re.I)

# SECTIONS parsing
# Matches a linker section header:  .name [(flags)] [addr] [AT(lma)] [ALIGN(...)] :
_SECT_HDR_RE = re.compile(
    r"^\s*(?P<name>(?:/DISCARD/|\.[\w.$*\-]*))\s*(?:.*?):",
    re.I,
)
# Matches the closing line of a section body:  } >VMA [AT> LMA]
_SECT_CLOSE_RE = re.compile(
    r"^\s*\}\s*>\s*(?P<vma>[A-Za-z_]\w*)(?:\s+AT\s*>\s*(?P<lma>[A-Za-z_]\w*))?",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "memory" in sample and ("origin" in sample or "length" in sample)


def _parse_sections(lines: Sequence[str]) -> list[dict]:
    """Parse the SECTIONS block and return a list of {name, vma, lma} dicts."""
    sections: list[dict] = []
    in_sections_block = False
    outer_brace_open = False
    current_name: str | None = None
    depth = 0  # brace depth inside the SECTIONS { } block

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("/*") or line.startswith("*") or line.startswith("//"):
            continue

        # Detect SECTIONS keyword
        if not in_sections_block:
            if re.match(r"^SECTIONS\s*(\{|$)", line, re.I):
                in_sections_block = True
                outer_brace_open = "{" in line
                depth = 0
            continue

        # Wait for the outer opening brace if it wasn't on the SECTIONS line
        if not outer_brace_open:
            if "{" in line:
                outer_brace_open = True
            continue

        # Section header at depth 0 (before counting this line's braces,
        # because the brace may be on the same line as the header, e.g. `.text : {`)
        if depth == 0:
            hdr_m = _SECT_HDR_RE.match(line)
            if hdr_m:
                name = hdr_m.group("name")
                if name != "/DISCARD/":
                    current_name = name

        # Count braces on this line
        opens  = line.count("{")
        closes = line.count("}")
        depth += opens - closes

        # Closing line: } >VMA [AT> LMA]  — depth just dropped to 0
        close_m = _SECT_CLOSE_RE.match(line)
        if close_m and depth == 0 and current_name:
            lma = close_m.group("lma")
            sections.append({
                "name": current_name,
                "vma":  close_m.group("vma"),
                "lma":  lma if lma else None,
            })
            current_name = None
            continue

        # End of the SECTIONS block itself
        if depth < 0:
            break

    return sections


def parse(lines: Sequence[str]) -> tuple[list[MemoryRegion], dict]:
    regions: list[MemoryRegion] = []
    extras: dict = {}
    in_memory = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("MEMORY"):
            in_memory = True
            continue
        if in_memory and stripped.startswith("}"):
            in_memory = False
            continue

        # Scan for stack/heap assignments outside the MEMORY block
        if not in_memory:
            m = _ASSIGN_RE.match(line)
            if m:
                try:
                    val = parse_byte_size(m.group("val"))
                    sym = m.group("name")
                    if _STACK_KEYS.search(sym):
                        extras["stack_size"] = val
                    if _HEAP_KEYS.search(sym):
                        extras["heap_size"] = val
                except ValueError:
                    pass
            continue

        match = MEMORY_LINE_RE.match(line)
        if not match:
            continue

        body = match.group("body")
        tokens = {m.group("key").lower(): m.group("value") for m in TOKEN_RE.finditer(body)}
        origin_token = tokens.get("origin") or tokens.get("org")
        length_token = tokens.get("length") or tokens.get("len")
        if not origin_token or not length_token:
            continue

        try:
            origin = parse_int(origin_token)
            length = parse_byte_size(length_token)
        except ValueError:
            continue

        if length <= 0:
            continue

        regions.append(
            MemoryRegion(
                name=match.group("name"),
                origin=origin,
                length=length,
                attrs=(match.group("attrs") or "").strip(),
            )
        )

    # Parse SECTIONS block
    sections = _parse_sections(lines)
    if sections:
        extras["sections"] = sections

    return regions, extras
