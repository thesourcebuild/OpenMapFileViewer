from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import jinja2

from .models import Analysis, Contribution, MemoryRegion
from .section_rules import MODULE_CLASS_RULES
from .stats import build_module_rows, compute_stats
from .utils import nice_size, object_name, region_kind as shared_region_kind


def pct(n: int, d: int) -> str:
    return "0.0%" if not d else f"{100.0 * n / d:.1f}%"


def size_with_hex(value: int) -> str:
    return f"{nice_size(value)} (0x{value:X})"


def classify_module(name: str) -> str:
    """Small, transparent embedded-oriented grouping used only for dashboard views."""
    lowered = (name or "").lower()
    for category, keywords in MODULE_CLASS_RULES.items():
        if any(t in lowered for t in keywords):
            return category
    return "Other"


def _build_jinja_env() -> jinja2.Environment:
    """Create and configure the Jinja2 environment for HTML report rendering."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller single-file bundle: template extracted under _MEIPASS/analyzer/
        template_dir = Path(sys._MEIPASS) / "analyzer"
    else:
        # Normal install or dev run: template sits alongside this module
        template_dir = Path(__file__).parent

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html"]),
        keep_trailing_newline=True,
    )
    # Custom filters
    env.filters["nice_size"] = nice_size
    env.filters["size_with_hex"] = size_with_hex
    env.filters["pct"] = pct  # usage in template: {{ n | pct(d) }}
    # Useful builtins as globals
    env.globals["min"] = min
    env.globals["max"] = max
    env.globals["pct"] = pct
    return env


def render_html(
    analysis: Analysis,
    top: int = 80,
    rom_capacity: int | None = None,
    ram_capacity: int | None = None,
) -> str:
    stats = compute_stats(analysis)
    total = int(stats["total_bytes"])
    by_class = stats["by_class"]
    by_section = stats["by_section"]
    by_object = stats["by_object"]
    by_archive = stats["by_archive"]
    by_source = stats["by_source"]
    symbols: List[Contribution] = stats["symbols"]  # type: ignore[assignment]

    # --- Class totals ---
    class_totals: Dict[str, int] = defaultdict(int)
    for row in by_class:
        class_totals[str(row.get("name", "other"))] += int(row.get("total", 0))
    code = class_totals.get("code", 0)
    rodata = class_totals.get("rodata", 0)
    rwdata = class_totals.get("data", 0)
    bss = class_totals.get("bss", 0)
    debug = class_totals.get("debug", 0)
    other = class_totals.get("other", 0)
    rom_image = code + rodata + rwdata
    ram_runtime = rwdata + bss

    # --- Region classification ---
    region_kind = lambda r: r.kind or shared_region_kind(
        r.name, r.attrs, r.origin, r.length
    )

    flash_regions = [r for r in analysis.memory_regions if region_kind(r) == "flash"]
    ram_regions = [r for r in analysis.memory_regions if region_kind(r) == "ram"]
    flash_cap = sum(r.length for r in flash_regions)
    ram_cap = sum(r.length for r in ram_regions)
    direct_flash_used = sum(r.used for r in flash_regions)
    direct_ram_used = sum(r.used for r in ram_regions)
    flash_used = direct_flash_used or rom_image
    ram_used = direct_ram_used if direct_ram_used else (rwdata + bss)

    flash_capacity_overridden = rom_capacity is not None
    ram_capacity_overridden = ram_capacity is not None
    if flash_capacity_overridden:
        flash_cap = max(rom_capacity or 0, 1)
    if ram_capacity_overridden:
        ram_cap = max(ram_capacity or 0, 1)
    if not flash_cap:
        flash_cap = flash_used or 1
    if not ram_cap:
        ram_cap = ram_used or 1

    # --- Notes ---
    flash_note = ""
    if flash_regions:
        region_names = ", ".join(r.name for r in flash_regions[:8])
        if direct_flash_used == 0 and rom_image:
            flash_note = (
                "No allocated sections were mapped directly inside the flash/non-volatile "
                "address range; usage is estimated from Code + RO data + RW init image."
            )
        else:
            flash_note = (
                "Boot image capacity is based on non-volatile regions detected in the linker map: "
                + region_names
                + ("." if len(flash_regions) <= 8 else ", ...")
            )
    if flash_capacity_overridden:
        suffix = f" Capacity overridden from the command line: {nice_size(flash_cap)}."
        flash_note = suffix.lstrip() if not flash_note else flash_note + suffix

    ram_note = ""
    if ram_regions:
        region_names = ", ".join(r.name for r in ram_regions[:8])
        ram_note = (
            "RAM capacity is based on RAM-like regions detected in the linker map: "
            + region_names
            + ("." if len(ram_regions) <= 8 else ", ...")
        )
    if ram_capacity_overridden:
        suffix = f" Capacity overridden from the command line: {nice_size(ram_cap)}."
        ram_note = suffix.lstrip() if not ram_note else ram_note + suffix

    # --- Capacity cards (passed as dicts; template renders via macro) ---
    flash_card = {
        "title": "Flash / ROM capacity",
        "used": flash_used,
        "cap": flash_cap,
        "percent": 100.0 * flash_used / flash_cap if flash_cap else 0.0,
        "breakdown": [("Code", code), ("RO data", rodata), ("RW init image", rwdata)],
        "note": flash_note,
    }
    ram_breakdown = [("RW data", rwdata), ("ZI/BSS/heap/stack", bss)]
    if direct_ram_used:
        non_data_ram = max(0, direct_ram_used - rwdata - bss)
        if non_data_ram > 0:
            ram_breakdown.append(("Code/RO in RAM", non_data_ram))
    ram_card = {
        "title": "RAM capacity",
        "used": ram_used,
        "cap": ram_cap,
        "percent": 100.0 * ram_used / ram_cap if ram_cap else 0.0,
        "breakdown": ram_breakdown,
        "note": ram_note,
    }

    # --- Top-level metric cards ---
    object_count = int(stats.get("object_count", 0))
    metrics = [
        {
            "label": "ROM image",
            "shown": nice_size(rom_image),
            "raw": f"{rom_image:,} B - ",
            "desc": "Code + RO data + RW init",
            "bytes": rom_image,
        },
        {
            "label": "RAM use",
            "shown": nice_size(ram_runtime),
            "raw": f"{ram_runtime:,} B - ",
            "desc": "RW data + ZI/BSS",
            "bytes": ram_runtime,
        },
        {
            "label": "Total RO",
            "shown": nice_size(code + rodata),
            "raw": f"{code+rodata:,} B - ",
            "desc": "Code + RO data",
            "bytes": code + rodata,
        },
        {
            "label": "Total RW",
            "shown": nice_size(rwdata + bss),
            "raw": f"{rwdata+bss:,} B - ",
            "desc": "RW data + ZI data",
            "bytes": rwdata + bss,
        },
        {
            "label": "Code",
            "shown": nice_size(code),
            "raw": f"{code:,} B - ",
            "desc": "Executable sections",
            "bytes": code,
        },
        {
            "label": "RO data",
            "shown": nice_size(rodata),
            "raw": f"{rodata:,} B - ",
            "desc": "Constants and tables",
            "bytes": rodata,
        },
        {
            "label": "RW data",
            "shown": nice_size(rwdata),
            "raw": f"{rwdata:,} B - ",
            "desc": "Initialised RAM",
            "bytes": rwdata,
        },
        {
            "label": "ZI / BSS",
            "shown": nice_size(bss),
            "raw": f"{bss:,} B - ",
            "desc": "Zero-initialised RAM",
            "bytes": bss,
        },
        {
            "label": "Debug / other",
            "shown": nice_size(debug + other),
            "raw": f"{debug+other:,} B - ",
            "desc": "Debug symbols (.elf only, not in firmware)",
            "bytes": debug + other,
        },
        {
            "label": "Objects",
            "shown": str(object_count),
            "raw": "",
            "desc": "Object/module rows",
            "bytes": None,
        },
    ]

    # --- Memory region rows ---
    from .validation import detect_layout_issues

    _, region_issues = detect_layout_issues(analysis)

    def get_region_status(r_name: str) -> str:
        issues = region_issues.get(r_name, {})
        if issues.get("overflow"):
            return "OVERFLOW"
        if issues.get("overlaps") or issues.get("section_overlaps"):
            return "OVERLAP"
        return "OK"

    region_rows = [
        {
            "name": region.name,
            "origin": f"0x{region.origin:08X}",
            "capacity": region.length,
            "used": region.used,
            "used_pct": pct(region.used, region.length),
            "status": get_region_status(region.name),
            "attrs": region.attrs,
        }
        for region in sorted(analysis.memory_regions, key=lambda r: r.origin)
    ]

    # --- Module rows with category and tag colour index ---
    module_rows = build_module_rows(by_object)
    tag_ids: Dict[str, int] = {}
    for row in module_rows:
        cat = classify_module(str(row.get("name", "")))
        row["category"] = cat
        tag_ids.setdefault(cat, len(tag_ids) % 8)
        row["tag_id"] = tag_ids[cat]

    # Full sorted lists for chart data (top 24 each)
    top_rom_full = sorted(module_rows, key=lambda r: int(r.get("rom", 0)), reverse=True)
    top_code_full = sorted(
        module_rows, key=lambda r: int(r.get("code", 0)), reverse=True
    )
    top_ram_full = sorted(module_rows, key=lambda r: int(r.get("ram", 0)), reverse=True)

    # Sliced lists for tables
    top_rom = top_rom_full[:top]
    top_code = top_code_full[:top]
    top_ram = top_ram_full[:top]

    # --- Category aggregation ---
    category_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in module_rows:
        cat = str(row.get("category", "Other"))
        for key in (
            "code",
            "rodata",
            "data",
            "bss",
            "debug",
            "other",
            "total",
            "rom",
            "ram",
        ):
            category_map[cat][key] += int(row.get(key, 0))
    cat_rows = [{"name": name, **parts} for name, parts in category_map.items()]
    cat_rows.sort(key=lambda r: int(r.get("total", 0)), reverse=True)

    # --- Symbol rows ---
    has_stack = any(c.local_stack is not None for c in symbols[:top])
    symbol_rows = []
    for contribution in symbols[:top]:
        row_s: Dict[str, Any] = {
            "name": contribution.symbol,
            "total": contribution.size,
            "section": contribution.section,
            "object": object_name(contribution.source),
            "address": (
                f"0x{contribution.address:08X}"
                if contribution.address is not None
                else ""
            ),
        }
        if has_stack:
            row_s["local_stack"] = (
                contribution.local_stack if contribution.local_stack is not None else -1
            )
            row_s["max_stack"] = (
                contribution.max_stack if contribution.max_stack is not None else -1
            )
        symbol_rows.append(row_s)

    # --- Stack entries (sorted by max depth) ---
    stack_entries = (
        sorted(analysis.stack_usage, key=lambda e: e.max_depth, reverse=True)[:top]
        if analysis.stack_usage
        else []
    )

    # --- Column definitions (list of {key, label} dicts) ---
    columns_common = [
        {"key": "name", "label": "Name"},
        {"key": "total", "label": "Total"},
        {"key": "code", "label": "Code"},
        {"key": "rodata", "label": "RO data"},
        {"key": "data", "label": "RW data"},
        {"key": "bss", "label": "ZI/BSS"},
        {"key": "debug", "label": "Debug"},
        {"key": "other", "label": "Other"},
        {"key": "bar", "label": "Share"},
    ]
    symbol_cols = [
        {"key": "name", "label": "Symbol"},
        {"key": "total", "label": "Size"},
    ]
    if has_stack:
        symbol_cols += [
            {"key": "local_stack", "label": "Local Stack"},
            {"key": "max_stack", "label": "Max Stack"},
        ]
    symbol_cols += [
        {"key": "section", "label": "Section"},
        {"key": "object", "label": "Object"},
        {"key": "address", "label": "Address"},
        {"key": "bar", "label": "Share"},
    ]

    # --- Chart data (serialised in template via tojson filter) ---
    chart_data = {
        "category": cat_rows,
        "topCode": top_code_full[:24],
        "topRom": top_rom_full[:24],
        "topRam": top_ram_full[:24],
        # ① Physical Address Space Map — one entry per memory region
        "addressSpace": [
            {
                "name": region.name,
                "origin": region.origin,
                "length": region.length,
                "used": region.used,
                "attrs": region.attrs,
                "overflow": region_issues.get(region.name, {}).get("overflow", False),
                "overlaps": region_issues.get(region.name, {}).get("overlaps", []),
                "section_overlaps": region_issues.get(region.name, {}).get(
                    "section_overlaps", []
                ),
            }
            for region in sorted(analysis.memory_regions, key=lambda r: r.origin)
        ],
        # ② ROM vs RAM Bubble Chart — one bubble per module
        "scatter": [
            {
                "name": row.get("name", ""),
                "rom": int(row.get("rom", 0)),
                "ram": int(row.get("ram", 0)),
                "total": int(row.get("total", 0)),
                "category": row.get("category", "Other"),
            }
            for row in sorted(
                module_rows, key=lambda r: int(r.get("total", 0)), reverse=True
            )[:80]
            if int(row.get("total", 0)) > 0
        ],
        # ③ Treemap — top 80 modules by total size
        "treemap": [
            {
                "name": row.get("name", ""),
                "rom": int(row.get("rom", 0)),
                "ram": int(row.get("ram", 0)),
                "total": int(row.get("total", 0)),
                "category": row.get("category", "Other"),
            }
            for row in sorted(
                module_rows, key=lambda r: int(r.get("total", 0)), reverse=True
            )[:80]
            if int(row.get("total", 0)) > 0
        ],
        # ④ Linker Section Donut — one slice per section
        "donut": [
            {"name": str(row.get("name", "")), "total": int(row.get("total", 0))}
            for row in list(by_section)
            if int(row.get("total", 0)) > 0
        ][:20],
        "linker": (
            {
                "name": analysis.linker_name,
                "format": analysis.linker_format,
                "content": analysis.linker_content,
                "regions": (
                    [
                        {
                            "name": r.name,
                            "origin": r.origin,
                            "length": r.length,
                            "attrs": r.attrs,
                        }
                        for r in analysis.linker_regions
                    ]
                    if analysis.linker_regions
                    else []
                ),
            }
            if analysis.linker_name
            else None
        ),
    }

    chip_config_name = None
    chip_hints = [h for h in analysis.format_hints if h.startswith("chip-config=")]
    if chip_hints:
        chip_config_name = chip_hints[0].partition("=")[2]

    basename = os.path.splitext(os.path.basename(analysis.input_file))[0]
    parser_hint = (
        ", ".join(analysis.format_hints)
        if analysis.format_hints
        else "best-effort linker map parser"
    )

    env = _build_jinja_env()
    template = env.get_template("template.html")
    return template.render(
        basename=basename,
        parser_hint=parser_hint,
        generated_at=analysis.generated_at,
        warnings=analysis.warnings,
        metrics=metrics,
        flash_card=flash_card,
        ram_card=ram_card,
        region_rows=region_rows,
        top_rom=top_rom,
        top_code=top_code,
        top_ram=top_ram,
        by_archive=list(by_archive)[:top],
        by_section=list(by_section)[:top],
        by_source=list(by_source)[:top],
        symbol_rows=symbol_rows,
        symbol_cols=symbol_cols,
        has_stack=has_stack,
        stack_entries=stack_entries,
        cat_rows=cat_rows,
        chart_data=chart_data,
        columns_common=columns_common,
        total=total,
        top=top,
        linker_name=analysis.linker_name,
        linker_format=analysis.linker_format,
        linker_content=analysis.linker_content,
        linker_regions=analysis.linker_regions,
        linker_extras=analysis.linker_extras,
        chip_config_name=chip_config_name,
        chip_regions=analysis.memory_regions if chip_config_name else None,
    )


def render_markdown(
    analysis: Analysis,
    rom_capacity: int | None = None,
    ram_capacity: int | None = None,
) -> str:
    stats = compute_stats(analysis)
    by_class = stats["by_class"]

    class_totals = defaultdict(int)
    for row in by_class:
        class_totals[str(row.get("name", "other"))] += int(row.get("total", 0))
    code = class_totals.get("code", 0)
    rodata = class_totals.get("rodata", 0)
    rwdata = class_totals.get("data", 0)
    bss = class_totals.get("bss", 0)
    debug = class_totals.get("debug", 0)
    other = class_totals.get("other", 0)

    rom_image = code + rodata + rwdata
    ram_runtime = rwdata + bss

    region_kind = lambda r: r.kind or shared_region_kind(
        r.name, r.attrs, r.origin, r.length
    )

    flash_regions = [
        region for region in analysis.memory_regions if region_kind(region) == "flash"
    ]
    ram_regions = [
        region for region in analysis.memory_regions if region_kind(region) == "ram"
    ]
    flash_cap = sum(region.length for region in flash_regions)
    ram_cap = sum(region.length for region in ram_regions)
    direct_flash_used = sum(region.used for region in flash_regions)
    direct_ram_used = sum(region.used for region in ram_regions)

    flash_used = direct_flash_used or rom_image
    ram_used = direct_ram_used if direct_ram_used else (rwdata + bss)

    if rom_capacity is not None:
        flash_cap = max(rom_capacity, 1)
    if ram_capacity is not None:
        ram_cap = max(ram_capacity, 1)

    flash_cap_str = nice_size(flash_cap) if flash_cap else "-"
    ram_cap_str = nice_size(ram_cap) if ram_cap else "-"
    flash_pct = pct(flash_used, flash_cap) if flash_cap else "-"
    ram_pct = pct(ram_used, ram_cap) if ram_cap else "-"

    md = []
    md.append("## 📊 Firmware Memory Usage Report")
    md.append(f"**Map File:** `{os.path.basename(analysis.input_file)}`  ")
    md.append(f"**Generated:** `{analysis.generated_at}`\n")

    md.append("### 💾 Memory Summary")
    md.append("| Memory Type | Used | Capacity | Utilization | Details |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    md.append(
        f"| **ROM (Flash)** | `{nice_size(flash_used)}` | `{flash_cap_str}` | **{flash_pct}** | Code + RO data + RW init image |"
    )
    md.append(
        f"| **RAM** | `{nice_size(ram_used)}` | `{ram_cap_str}` | **{ram_pct}** | RW data + ZI/BSS/heap/stack |"
    )
    md.append("")

    total_mem = code + rodata + rwdata + bss + debug + other
    md.append("### 🔍 Breakdown by Class")
    md.append("| Class | Size | Share | Description |")
    md.append("| :--- | :--- | :--- | :--- |")
    md.append(
        f"| **Code** | `{nice_size(code)}` | {pct(code, total_mem)} | Executable instructions |"
    )
    md.append(
        f"| **RO Data** | `{nice_size(rodata)}` | {pct(rodata, total_mem)} | Read-only constants |"
    )
    md.append(
        f"| **RW Data** | `{nice_size(rwdata)}` | {pct(rwdata, total_mem)} | Initialized RAM data |"
    )
    md.append(
        f"| **ZI / BSS** | `{nice_size(bss)}` | {pct(bss, total_mem)} | Zero-initialized RAM |"
    )
    if debug:
        md.append(
            f"| **Debug** | `{nice_size(debug)}` | {pct(debug, total_mem)} | Debug symbols |"
        )
    if other:
        md.append(
            f"| **Other** | `{nice_size(other)}` | {pct(other, total_mem)} | Unclassified or other data |"
        )
    md.append("")

    if analysis.stack_usage:
        md.append("### 🥞 Stack Usage Analysis (Top 5)")
        md.append(
            "| Rank | Function | Local Stack | Max Stack Depth | Source File:Line | Type |"
        )
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        shown_stack = sorted(
            analysis.stack_usage, key=lambda e: e.max_depth, reverse=True
        )[:5]
        for index, entry in enumerate(shown_stack, start=1):
            line_part = f":{entry.line}" if entry.line else ""
            md.append(
                f"| {index} | `{entry.symbol}` | `{nice_size(entry.local_size)}` | **`{nice_size(entry.max_depth)}`** | `{entry.source_file}{line_part}` | `{entry.qualifier}` |"
            )
        md.append("")

    return "\n".join(md)
