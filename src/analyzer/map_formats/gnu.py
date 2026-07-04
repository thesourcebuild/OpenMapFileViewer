from __future__ import annotations

import re
from typing import Sequence

from ..models import Analysis, Contribution, MemoryRegion
from ..utils import normalize_source, parse_int, section_class
from .base import append_hint

FORMAT_NAME = "gnu"
ALIASES: tuple[str, ...] = ()

MEMORY_LINE_RE = re.compile(
    r"^\s*(?P<name>\S+)\s+(?P<origin>0x[0-9A-Fa-f]+|[0-9A-Fa-f]+)\s+(?P<length>0x[0-9A-Fa-f]+|[0-9A-Fa-f]+)\s*(?P<attrs>.*)$"
)
GNU_SECTION_RE = re.compile(
    r"^(?P<section>\.[\w.$/+-]+)\s+(?P<addr>0x[0-9A-Fa-f]+)\s+(?P<size>0x[0-9A-Fa-f]+)(?:\s+(?P<source>.+?))?\s*$"
)
GNU_CONT_RE = re.compile(
    r"^\s+(?P<addr>0x[0-9A-Fa-f]+)\s+(?P<size>0x[0-9A-Fa-f]+)(?:\s+(?P<source>.+?))?\s*$"
)
GNU_SYMBOL_RE = re.compile(
    r"^\s+(?P<addr>0x[0-9A-Fa-f]+)\s+(?P<symbol>[A-Za-z_][\w.]*)\s*(?:=.*)?$"
)
GNU_SECTION_ONLY_RE = re.compile(
    r"^(?P<section>\.[\w.$/+-]+)\s*$"
)
GNU_INPUT_SEC_RE = re.compile(
    r"^\s+(?P<section>\.[\w.$/+-]+)\s+(?P<addr>0x[0-9A-Fa-f]+)\s+(?P<size>0x[0-9A-Fa-f]+)(?:\s+(?P<source>.+?))?\s*$"
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "memory configuration" in sample and "linker script and memory map" in sample


def resolve_symbols(
    contrib: Contribution,
    symbols_list: list[tuple[str, int]],
    analysis: Analysis,
    min_size: int,
) -> None:
    if not symbols_list:
        if contrib.size >= min_size:
            analysis.contributions.append(contrib)
        return

    # Sort symbols by address
    symbols_list.sort(key=lambda x: x[1])
    contrib_start = contrib.address
    contrib_end = contrib.address + contrib.size

    # Remove duplicates or symbols at the same address
    unique_symbols = []
    seen_addresses = set()
    for name, addr in symbols_list:
        if addr not in seen_addresses:
            unique_symbols.append((name, addr))
            seen_addresses.add(addr)

    # 1. Padding before first symbol
    first_sym_addr = unique_symbols[0][1]
    if first_sym_addr > contrib_start:
        padding_size = first_sym_addr - contrib_start
        if padding_size >= min_size:
            analysis.contributions.append(
                Contribution(
                    section=contrib.section,
                    address=contrib_start,
                    size=padding_size,
                    source=contrib.source,
                    kind=contrib.kind,
                    line_no=contrib.line_no,
                )
            )

    # 2. Add each symbol contribution
    for i in range(len(unique_symbols)):
        sym_name, sym_addr = unique_symbols[i]
        if i + 1 < len(unique_symbols):
            next_addr = unique_symbols[i + 1][1]
            sym_size = next_addr - sym_addr
        else:
            sym_size = contrib_end - sym_addr

        if sym_size >= min_size and sym_size > 0:
            analysis.contributions.append(
                Contribution(
                    section=contrib.section,
                    address=sym_addr,
                    size=sym_size,
                    source=contrib.source,
                    symbol=sym_name,
                    kind=contrib.kind,
                    line_no=contrib.line_no,
                )
            )


def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
    in_memory = False
    current_section = ""
    seen_memory_header = False
    seen_linker_map = False

    active_contrib = None
    active_symbols = []

    pending_section = None
    pending_line_no = 0
    parent_section_end = None

    def flush_active():
        if active_contrib:
            resolve_symbols(active_contrib, active_symbols, analysis, min_size)

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("Memory Configuration"):
            in_memory = True
            seen_memory_header = True
            continue
        if in_memory and stripped.startswith("Linker script and memory map"):
            in_memory = False
            seen_linker_map = True
            continue
        if in_memory:
            if stripped.startswith("Name") or stripped.startswith("*"):
                continue
            match = MEMORY_LINE_RE.match(line)
            if not match:
                continue
            name = match.group("name")
            if name.lower() in {"default", "*default*"}:
                continue
            try:
                analysis.memory_regions.append(
                    MemoryRegion(
                        name=name,
                        origin=parse_int(match.group("origin")),
                        length=parse_int(match.group("length")),
                        attrs=match.group("attrs").strip(),
                    )
                )
            except ValueError:
                pass
            continue

        if not seen_linker_map:
            continue

        if pending_section:
            match = GNU_CONT_RE.match(line)
            if match:
                flush_active()
                active_symbols = []
                current_section = pending_section
                addr = parse_int(match.group("addr"))
                size = parse_int(match.group("size"))
                if parent_section_end is not None and addr < parent_section_end and addr + size > parent_section_end:
                    size = max(0, parent_section_end - addr)
                source = normalize_source(match.group("source") or "<section total>")

                active_contrib = Contribution(
                    current_section,
                    addr,
                    size,
                    source,
                    kind=section_class(current_section),
                    line_no=pending_line_no,
                )
                pending_section = None
                continue
            else:
                pending_section = None

        match = GNU_SECTION_RE.match(line)
        if match:
            flush_active()
            active_symbols = []

            current_section = match.group("section")
            addr = parse_int(match.group("addr"))
            size = parse_int(match.group("size"))
            source = "<section total>"

            parent_section_end = addr + size

            active_contrib = Contribution(
                current_section,
                addr,
                size,
                source,
                kind=section_class(current_section),
                line_no=line_no,
            )
            continue

        match = GNU_INPUT_SEC_RE.match(line)
        if match:
            flush_active()
            active_symbols = []

            addr = parse_int(match.group("addr"))
            size = parse_int(match.group("size"))
            if parent_section_end is not None and addr < parent_section_end and addr + size > parent_section_end:
                size = max(0, parent_section_end - addr)
            source = normalize_source(match.group("source") or "<unknown>")

            sec_name = current_section or match.group("section")
            active_contrib = Contribution(
                sec_name,
                addr,
                size,
                source,
                kind=section_class(sec_name),
                line_no=line_no,
            )
            continue

        match = GNU_CONT_RE.match(line)
        if match and current_section:
            flush_active()
            active_symbols = []

            addr = parse_int(match.group("addr"))
            size = parse_int(match.group("size"))
            if parent_section_end is not None and addr < parent_section_end and addr + size > parent_section_end:
                size = max(0, parent_section_end - addr)
            source = normalize_source(match.group("source") or "<unknown>")

            active_contrib = Contribution(
                current_section,
                addr,
                size,
                source,
                kind=section_class(current_section),
                line_no=line_no,
            )
            continue

        match_sec_only = GNU_SECTION_ONLY_RE.match(line)
        if match_sec_only:
            pending_section = match_sec_only.group("section")
            pending_line_no = line_no
            continue

        if active_contrib and current_section:
            match = GNU_SYMBOL_RE.match(line)
            if match:
                sym_addr = parse_int(match.group("addr"))
                sym_name = match.group("symbol")
                if active_contrib.address <= sym_addr < active_contrib.address + active_contrib.size:
                    active_symbols.append((sym_name, sym_addr))

    flush_active()

    if seen_memory_header:
        append_hint(analysis, "GNU ld memory configuration")
    if seen_linker_map:
        append_hint(analysis, "GNU/Clang linker map")
