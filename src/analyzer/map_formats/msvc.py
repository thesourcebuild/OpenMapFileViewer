from __future__ import annotations

import re
from typing import Sequence

from ..models import Analysis, Contribution
from ..utils import parse_int, section_class

FORMAT_NAME = "msvc"
ALIASES: tuple[str, ...] = ()

MSVC_SECTION_RE = re.compile(
    r"^\s*(?P<section_index>[0-9A-Fa-f]{4}):(?P<offset>[0-9A-Fa-f]{8})\s+(?P<size>[0-9A-Fa-f]+)H?\s+(?P<name>\S+)\s+(?P<class>CODE|DATA|BSS|CONST|TLS)\b",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "preferred load address is" in sample and "publics by value" in sample


def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
    for line_no, line in enumerate(lines, 1):
        match = MSVC_SECTION_RE.match(line)
        if not match:
            continue
        section = match.group("name")
        size = parse_int(match.group("size"), default_base=16)
        if size >= min_size and size > 0:
            analysis.contributions.append(
                Contribution(section, None, size, "<section total>", kind=section_class(match.group("class")), line_no=line_no)
            )
