from __future__ import annotations

import re
from typing import Sequence

from ..models import Analysis, Contribution
from ..utils import normalize_source, parse_int, section_class

FORMAT_NAME = "ti"
ALIASES: tuple[str, ...] = ()

TI_SECTION_RE = re.compile(
    r"^\s*(?P<section>\.?[A-Za-z_.$][\w.$]*)\s+(?P<page>\d+)\s+(?P<addr>[0-9A-Fa-f]{4,16})\s+(?P<size>[0-9A-Fa-f]{1,16})\s*(?P<attrs>.*)$"
)
TI_MEMBER_RE = re.compile(
    r"^\s*(?P<addr>[0-9A-Fa-f]{4,16})\s+(?P<size>[0-9A-Fa-f]{1,16})\s+(?P<source>.+?\.(?:obj|o|lib|a)(?:\([^)]*\))?).*$",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "section allocation map" in sample and ("ti" in sample or "linker" in sample)


def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
    current_section = ""

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        match = TI_SECTION_RE.match(line)
        if match and not stripped.lower().startswith(("name", "----")):
            section = match.group("section")
            try:
                addr = parse_int(match.group("addr"), default_base=16)
                size = parse_int(match.group("size"), default_base=16)
            except ValueError:
                addr = None
                size = 0
            if size >= min_size and size > 0:
                analysis.contributions.append(
                    Contribution(section, addr, size, "<section total>", kind=section_class(section), line_no=line_no)
                )
                current_section = section
            continue

        match = TI_MEMBER_RE.match(line) if current_section else None
        if match:
            try:
                addr = parse_int(match.group("addr"), default_base=16)
                size = parse_int(match.group("size"), default_base=16)
            except ValueError:
                addr = None
                size = 0
            if size >= min_size and size > 0:
                analysis.contributions.append(
                    Contribution(
                        current_section,
                        addr,
                        size,
                        normalize_source(match.group("source")),
                        kind=section_class(current_section),
                        line_no=line_no,
                    )
                )
