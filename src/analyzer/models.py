from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Contribution:
    section: str
    address: Optional[int]
    size: int
    source: str = "<unknown>"
    symbol: str = ""
    kind: str = ""
    line_no: int = 0
    local_stack: Optional[int] = None
    max_stack: Optional[int] = None


@dataclass
class MemoryRegion:
    name: str
    origin: int
    length: int
    attrs: str = ""
    used: int = 0
    kind: str = ""


@dataclass
class StackUsageEntry:
    symbol: str
    local_size: int
    max_depth: int
    source_file: str
    line: int
    qualifier: str = "static"


@dataclass
class Analysis:
    input_file: str
    generated_at: str
    format_hints: List[str] = field(default_factory=list)
    memory_regions: List[MemoryRegion] = field(default_factory=list)
    contributions: List[Contribution] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stack_usage: List[StackUsageEntry] = field(default_factory=list)
    linker_name: Optional[str] = None
    linker_format: Optional[str] = None
    linker_content: Optional[str] = None
    linker_regions: List[MemoryRegion] = field(default_factory=list)
    linker_extras: Dict[str, int] = field(default_factory=dict)
