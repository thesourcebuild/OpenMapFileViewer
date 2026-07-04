from __future__ import annotations

import re
from typing import Sequence

from ..models import Analysis, Contribution, MemoryRegion
from ..utils import normalize_source, parse_int, section_class
from .base import append_hint

FORMAT_NAME = "keil"
ALIASES = ("arm",)

ARM_EXEC_RE = re.compile(
    r"Execution Region\s+(?P<name>\S+)\s+\((?:Exec\s+)?Base:\s*(?P<base>0x[0-9A-Fa-f]+)(?:,\s*Load\s+base:[^,]+)?,\s*Size:\s*(?P<size>0x[0-9A-Fa-f]+|\d+)(?:,\s*Max:\s*(?P<max>0x[0-9A-Fa-f]+|\d+))?.*?\)",
    re.I,
)
ARM_LOAD_RE = re.compile(
    r"Load Region\s+(?P<name>\S+)\s+\(Base:\s*(?P<base>0x[0-9A-Fa-f]+),\s*Size:\s*(?P<size>0x[0-9A-Fa-f]+|\d+)(?:,\s*Max:\s*(?P<max>0x[0-9A-Fa-f]+|\d+))?.*?\)",
    re.I,
)
ARM_SYMBOL_RE = re.compile(
    r"^\s*(?P<symbol>\S.*?)\s+(?P<value>0x[0-9A-Fa-f]+)\s+(?P<type>Code|Data|Zero|Number|Thumb|ARM|Section|Object|Function)\b\s+(?P<size>0x[0-9A-Fa-f]+|\d+)\s+(?P<source>\S+\.(?:o|obj|a|lib)(?:\([^)]*\))?)?\s*$",
    re.I,
)
KEIL_OBJECT_RE = re.compile(
    r"^\s*(?P<code>\d+)\s+(?P<incdata>\d+)\s+(?P<ro>\d+)\s+(?P<rw>\d+)\s+(?P<zi>\d+)\s+(?P<debug>\d+)\s+(?P<object>\S+\.(?:o|obj|a|lib)(?:\([^)]*\))?)\s*$",
    re.I,
)
KEIL_SIMPLE_OBJECT_RE = re.compile(
    r"^\s*(?P<code>\d+)\s+(?P<ro>\d+)\s+(?P<rw>\d+)\s+(?P<zi>\d+)\s+(?P<object>\S+\.(?:o|obj|a|lib)(?:\([^)]*\))?)\s*$",
    re.I,
)
KEIL_SPECIAL_RE = re.compile(
    r"^\s*(?P<code>\d+)\s+(?P<incdata>\d+)\s+(?P<ro>\d+)\s+(?P<rw>\d+)\s+(?P<zi>\d+)\s+(?P<debug>\d+)\s+\(incl\.\s+(?P<kind>Padding|Generated)\)\s*$",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "execution region" in sample or "load region" in sample or "image symbol table" in sample


def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
    current_region = ""
    saw_region_data = False

    for line_no, line in enumerate(lines, 1):
        for regex, region_kind in ((ARM_EXEC_RE, "execution-region"), (ARM_LOAD_RE, "load-region")):
            match = regex.search(line)
            if not match:
                continue
            saw_region_data = True
            name = match.group("name")
            base = parse_int(match.group("base"))
            size = parse_int(match.group("size"))
            max_val = parse_int(match.group("max")) if match.group("max") else 0
            if not any(region.origin == base for region in analysis.memory_regions):
                analysis.memory_regions.append(MemoryRegion(name=name, origin=base, length=max_val, attrs=region_kind, used=size))
            analysis.contributions.append(
                Contribution(name, base, size, "<region total>", kind=region_kind, line_no=line_no)
            )
            current_region = name

        match = ARM_SYMBOL_RE.match(line)
        if match:
            saw_region_data = True
            symbol = match.group("symbol").strip()
            size = parse_int(match.group("size"))
            addr = parse_int(match.group("value"))
            value_type = match.group("type").lower()
            source = normalize_source(match.group("source") or "<unknown>")
            if value_type == "section":
                continue
            section = current_region or value_type
            if value_type in {"code", "thumb", "arm", "function"}:
                kind = "code"
            elif value_type == "data":
                kind = "data"
            elif value_type == "zero":
                kind = "bss"
            else:
                kind = "other"
            if size >= min_size:
                analysis.contributions.append(
                    Contribution(section, addr, size, source, symbol=symbol, kind=kind, line_no=line_no)
                )
            continue

        match = KEIL_OBJECT_RE.match(line)
        if match:
            values = [
                ("CODE", int(match.group("code"))),
                ("RO DATA", int(match.group("ro"))),
                ("RW DATA", int(match.group("rw"))),
                ("ZI DATA", int(match.group("zi"))),
                ("DEBUG", int(match.group("debug"))),
            ]
            for section, size in values:
                if size >= min_size and size > 0:
                    analysis.contributions.append(
                        Contribution(section, None, size, match.group("object"), kind=section_class(section), line_no=line_no)
                    )
            continue

        match = KEIL_SIMPLE_OBJECT_RE.match(line)
        if match:
            values = [
                ("CODE", int(match.group("code"))),
                ("RO DATA", int(match.group("ro"))),
                ("RW DATA", int(match.group("rw"))),
                ("ZI DATA", int(match.group("zi"))),
            ]
            for section, size in values:
                if size >= min_size and size > 0:
                    analysis.contributions.append(
                        Contribution(section, None, size, match.group("object"), kind=section_class(section), line_no=line_no)
                    )
            continue

        match = KEIL_SPECIAL_RE.match(line)
        if match:
            name = f"(incl. {match.group('kind')})"
            values = [
                ("CODE", int(match.group("code"))),
                ("RO DATA", int(match.group("ro"))),
                ("RW DATA", int(match.group("rw"))),
                ("ZI DATA", int(match.group("zi"))),
                ("DEBUG", int(match.group("debug"))),
            ]
            for section, size in values:
                if size >= min_size and size > 0:
                    analysis.contributions.append(
                        Contribution(section, None, size, name, kind=section_class(section), line_no=line_no)
                    )

    if saw_region_data:
        append_hint(analysis, "ARM/Keil load/execution regions")
