from __future__ import annotations

import os
import re
from typing import Sequence

from ..models import Analysis, Contribution, MemoryRegion
from ..utils import section_class
from .base import append_hint

FORMAT_NAME = "iar"
ALIASES: tuple[str, ...] = ()

IAR_MODULE_RE = re.compile(
    r"^\s*(?P<module>\S+\.(?:o|obj|a|lib))\s+(?P<code>\d+)\s+(?P<ro>\d+)\s+(?P<rw>\d+)\s+(?P<zi>\d+)\s*$",
    re.I,
)
IAR_SUMMARY_RE = re.compile(
    r"^\s*(?P<section>CODE|RO DATA|RW DATA|ZI DATA|CONST|DATA|BSS)\s+(?P<size>\d+)\s+(?P<module>\S+\.(?:o|obj|a|lib)(?:\([^)]*\))?)\s*$",
    re.I,
)


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return (
        "iar universal linker" in sample
        or "iar linker" in sample
        or ("module summary" in sample and ("readonly code memory" in sample or ".o" in sample or ".obj" in sample))
    )


def parse(lines: Sequence[str], analysis: Analysis, min_size: int = 0) -> None:
    # Modern IAR placement summary regexes
    IAR_PLACEMENT_RE = re.compile(
        r"^\s{2,4}(?P<section>[\w. \x24#-]+?)\s{2,}(?:(?P<kind>inited|zero|ro\s+code|const|uninit)\s+)?(?P<addr>0x[0-9a-fA-F\x27]+)\s+(?:(?P<align>\d+|--)\s+)?(?P<size>0x[0-9a-fA-F]+)\s+(?P<object>.+?)(?:\s+\[\d+\])?\s*$"
    )
    IAR_INDEX_RE = re.compile(
        r"^\s*\[(?P<idx>\d+)\]\s*=\s*(?P<path>.+?)\s*$"
    )
    IAR_REGION_RE = re.compile(
        r'^"(?P<name>\w+)":\s+place\s+in\s+\[from\s+(?P<start>0x[0-9a-fA-F\x27]+)\s+to\s+(?P<end>0x[0-9a-fA-F\x27]+)\]',
        re.I
    )

    # First pass: build index mappings and extract memory regions
    index_map = {}
    for line in lines:
        m_idx = IAR_INDEX_RE.match(line)
        if m_idx:
            index_map[m_idx.group("idx")] = m_idx.group("path").strip()
            continue

        m_reg = IAR_REGION_RE.match(line)
        if m_reg:
            name = m_reg.group("name")
            start = int(m_reg.group("start").replace("'", ""), 16)
            end = int(m_reg.group("end").replace("'", ""), 16)
            length = end - start + 1
            
            # Classify as ROM or RAM based on address range
            region_name = name
            if start < 0x20000000:
                region_name += "_ROM"
            else:
                region_name += "_RAM"
                
            if not any(r.origin == start for r in analysis.memory_regions):
                analysis.memory_regions.append(
                    MemoryRegion(name=region_name, origin=start, length=length, attrs="placement-region")
                )

    # Second pass: parse placement summary contributions
    in_placement_summary = False
    contributions_count = 0

    for line_no, line in enumerate(lines, 1):
        if "-------            ----         -------  ---------    ----  ------" in line:
            in_placement_summary = True
            continue
        if in_placement_summary and line.startswith("Unused ranges:"):
            in_placement_summary = False
            break

        if not in_placement_summary:
            continue

        m = IAR_PLACEMENT_RE.match(line)
        if m:
            section = m.group("section").strip()
            kind_str = m.group("kind")
            addr_str = m.group("addr").replace("'", "")
            size_str = m.group("size").replace("'", "")
            obj_raw = m.group("object").strip()

            # Deduplication rules
            if obj_raw in ("<Init block>", "<Block tail>"):
                continue

            # Resolve object using index_map
            obj_match = re.match(r"^(?P<name>.+?)\s+\[(?P<idx>\d+)\]$", obj_raw)
            if obj_match:
                obj_name = obj_match.group("name")
                idx = obj_match.group("idx")
                if idx in index_map:
                    prefix = index_map[idx]
                    if prefix.endswith(".dir"):
                        resolved_obj = os.path.join(prefix, obj_name)
                    elif prefix.endswith(".a") or prefix.endswith(".lib"):
                        resolved_obj = f"{prefix}({obj_name})"
                    else:
                        resolved_obj = f"{prefix}/{obj_name}"
                else:
                    resolved_obj = obj_raw
            else:
                resolved_obj = obj_raw

            if resolved_obj in {"- Linker created -", "<Block>"}:
                resolved_obj = "<linker/generated>"

            addr = int(addr_str, 16)
            size = int(size_str, 16)

            if size < min_size:
                continue

            # Determine kind (standard category)
            kind = "other"
            if kind_str:
                kind_str_clean = kind_str.lower().strip()
                if kind_str_clean == "ro code":
                    kind = "code"
                elif kind_str_clean == "const":
                    kind = "rodata"
                elif kind_str_clean == "inited":
                    kind = "data"
                elif kind_str_clean in ("zero", "uninit"):
                    kind = "bss"
            else:
                sec_lower = section.lower()
                if "stack" in sec_lower or "heap" in sec_lower:
                    kind = "bss"
                else:
                    kind = section_class(section)

            analysis.contributions.append(
                Contribution(
                    section=section,
                    address=addr,
                    size=size,
                    source=resolved_obj,
                    kind=kind,
                    line_no=line_no
                )
            )
            contributions_count += 1

    # If we parsed contributions from the placement summary, we are done
    if contributions_count > 0:
        append_hint(analysis, "IAR placement summary")
        return

    # Fallback to legacy parser
    for line_no, line in enumerate(lines, 1):
        match = IAR_MODULE_RE.match(line)
        if match:
            module = match.group("module")
            for section, key in (("CODE", "code"), ("RODATA", "ro"), ("DATA", "rw"), ("BSS", "zi")):
                size = int(match.group(key))
                if size >= min_size and size > 0:
                    analysis.contributions.append(
                        Contribution(section, None, size, module, kind=section_class(section), line_no=line_no)
                    )
            continue

        match = IAR_SUMMARY_RE.match(line)
        if match:
            section = match.group("section")
            size = int(match.group("size"))
            if size >= min_size and size > 0:
                analysis.contributions.append(
                    Contribution(section, None, size, match.group("module"), kind=section_class(section), line_no=line_no)
                )

