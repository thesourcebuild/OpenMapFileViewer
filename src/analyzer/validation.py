from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import Analysis
from .utils import nice_size


def detect_layout_issues(analysis: Analysis) -> Tuple[List[str], Dict[str, Any]]:
    """
    Analyzes memory regions and section contributions to detect layout issues:
    1. Overlapping physical memory regions.
    2. Memory region overflows.
    3. Overlapping linker output sections.
    4. Proximity or collision between stack and heap.
    
    Returns:
        warnings: List of string warning messages to be logged/displayed.
        region_issues: Dict mapping region name to its specific issues (overflow, overlaps, section_overlaps).
    """
    warnings: List[str] = []
    region_issues: Dict[str, Any] = {}

    # Initialize tracking for each region
    for r in analysis.memory_regions:
        region_issues[r.name] = {
            "overflow": False,
            "overlaps": [],
            "section_overlaps": [],
        }

    # 1. Detect physical memory region overlaps
    regions = sorted(analysis.memory_regions, key=lambda r: r.origin)
    for i in range(len(regions)):
        r1 = regions[i]
        if r1.length <= 0:
            continue
        for j in range(i + 1, len(regions)):
            r2 = regions[j]
            if r2.length <= 0:
                continue
            # Check if they intersect
            if r1.origin <= r2.origin < r1.origin + r1.length:
                overlap_size = min(r1.origin + r1.length, r2.origin + r2.length) - r2.origin
                msg = (
                    f"Memory Region '{r1.name}' (0x{r1.origin:08X}-0x{r1.origin+r1.length:08X}) "
                    f"overlaps with '{r2.name}' (0x{r2.origin:08X}-0x{r2.origin+r2.length:08X}) "
                    f"by {nice_size(overlap_size)}."
                )
                warnings.append(msg)
                region_issues[r1.name]["overlaps"].append(r2.name)
                region_issues[r2.name]["overlaps"].append(r1.name)

    # 2. Detect memory region overflows
    for r in analysis.memory_regions:
        if r.length > 0 and r.used > r.length:
            msg = (
                f"Memory Region '{r.name}' overflowed by {nice_size(r.used - r.length)} "
                f"({nice_size(r.used)} used / {nice_size(r.length)} capacity)."
            )
            warnings.append(msg)
            region_issues[r.name]["overflow"] = True

    # 3. Detect overlapping output sections
    # Find bounding box (start and end) for each distinct section name
    from .utils import section_class
    section_bounds: Dict[str, List[int]] = {}
    for c in analysis.contributions:
        if c.address is None or c.size <= 0 or c.source == "<region total>":
            continue
        sec = c.section
        # Skip debug/non-allocated sections to avoid false positive overlap warnings
        if section_class(sec) == "debug":
            continue
        start = c.address
        end = c.address + c.size
        if sec not in section_bounds:
            section_bounds[sec] = [start, end]
        else:
            section_bounds[sec][0] = min(section_bounds[sec][0], start)
            section_bounds[sec][1] = max(section_bounds[sec][1], end)

    sorted_sections = sorted(
        [
            {"name": name, "start": bounds[0], "end": bounds[1], "size": bounds[1] - bounds[0]}
            for name, bounds in section_bounds.items()
        ],
        key=lambda s: s["start"],
    )

    # Sort individual contributions by address to check for actual physical overlaps
    valid_contribs = []
    for c in analysis.contributions:
        if c.address is None or c.size <= 0 or c.source == "<region total>":
            continue
        # Skip non-allocated sections (debug, metadata, etc. - not loaded into memory)
        kind = c.kind or section_class(c.section)
        if kind == "debug":
            continue
        valid_contribs.append(c)
    valid_contribs.sort(key=lambda x: x.address)

    detected_overlaps = set()
    for i in range(len(valid_contribs)):
        c1 = valid_contribs[i]
        c1_start = c1.address
        c1_end = c1.address + c1.size
        for j in range(i + 1, len(valid_contribs)):
            c2 = valid_contribs[j]
            if c2.address >= c1_end:
                break
            # Overlap exists! Check if sections are different
            if c1.section != c2.section:
                overlap_start = max(c1_start, c2.address)
                overlap_end = min(c1_end, c2.address + c2.size)
                overlap_size = overlap_end - overlap_start
                if overlap_size <= 0:
                    continue
                pair = tuple(sorted([c1.section, c2.section]))
                if pair not in detected_overlaps:
                    detected_overlaps.add(pair)
                    msg = (
                        f"Linker Section '{c1.section}' overlaps with '{c2.section}' "
                        f"in physical memory by {nice_size(overlap_size)} at address 0x{c2.address:08X}."
                    )
                    warnings.append(msg)
                    
                    # Link warning to corresponding region(s)
                    for r in analysis.memory_regions:
                        if r.length > 0 and r.origin <= c2.address < r.origin + r.length:
                            region_issues[r.name]["section_overlaps"].append(f"{c1.section} & {c2.section}")

    # 4. Detect Stack-Heap proximity and collision
    stack_info = None
    heap_info = None
    for s in sorted_sections:
        name = s["name"].lower()
        if "stack" in name:
            stack_info = s
        elif "heap" in name:
            heap_info = s

    if stack_info and heap_info:
        s_start, s_end = stack_info["start"], stack_info["end"]
        h_start, h_end = heap_info["start"], heap_info["end"]
        
        # Overlap check
        if max(s_start, h_start) < min(s_end, h_end):
            overlap_size = min(s_end, h_end) - max(s_start, h_start)
            msg = (
                f"Stack section '{stack_info['name']}' (0x{s_start:08X}-0x{s_end:08X}, size: {nice_size(stack_info['size'])}) "
                f"and Heap section '{heap_info['name']}' (0x{h_start:08X}-0x{h_end:08X}, size: {nice_size(heap_info['size'])}) "
                f"overlap by {nice_size(overlap_size)}!"
            )
            warnings.append(msg)
        else:
            # Proximity check (gap size)
            dist = 0
            if s_start >= h_end:
                dist = s_start - h_end
            elif h_start >= s_end:
                dist = h_start - s_end
            
            if dist < 1024:
                msg = (
                    f"Stack section '{stack_info['name']}' (0x{s_start:08X}-0x{s_end:08X}, size: {nice_size(stack_info['size'])}) "
                    f"and Heap section '{heap_info['name']}' (0x{h_start:08X}-0x{h_end:08X}, size: {nice_size(heap_info['size'])}) "
                    f"are dangerously close (gap of {nice_size(dist)}). Risk of runtime stack-heap collision."
                )
                warnings.append(msg)

    return warnings, region_issues
