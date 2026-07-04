#!/usr/bin/env python3
"""
Mapfile Analyzer

A dependency-free Python CLI that parses linker map files and generates a
self-contained HTML report with detailed memory, section, object, archive,
source, and symbol/function statistics.

Supported best-effort formats:
  - GNU ld / GCC / Clang linker map files
  - ARM/Keil/armclang map files containing Execution Region / Image Symbol Table
  - IAR-style map files containing section/module summaries

Usage:
  python src/openmapfileanalyzer.py firmware.map -o report.html
  python src/openmapfileanalyzer.py firmware.map -o report.html --json report.json
  python src/openmapfileanalyzer.py firmware.map --csv
  python src/openmapfileanalyzer.py firmware.map --top 100 --min-size 16
  python src/openmapfileanalyzer.py firmware.map --linker-file lscript.ld
  python src/openmapfileanalyzer.py firmware.map --format auto
  python src/openmapfileanalyzer.py firmware.map --format gnu
  python src/openmapfileanalyzer.py firmware.map --format keil
  python src/openmapfileanalyzer.py firmware.map --format iar
  python src/openmapfileanalyzer.py firmware.map --format ti
  python src/openmapfileanalyzer.py firmware.map --format msvc
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, Sequence


from version import __version__

from analyzer import SUPPORTED_FORMATS, parse_map, render_html, to_jsonable
from analyzer.stats import build_module_rows, compute_stats
from analyzer.utils import parse_byte_size


class _VersionHelpParser(argparse.ArgumentParser):
    def format_help(self):
        return f"Version: {__version__}\n\n{super().format_help()}"

    def error(self, message):
        sys.stderr.write(f"Version: {__version__}\n\n")
        super().error(message)

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = _VersionHelpParser(description="Generate a detailed HTML report from a linker map file.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("mapfile", type=Path, help="Input .map file")
    ap.add_argument("-o", "--output", type=Path, help="Output HTML path. Defaults to <mapfile>.html")
    ap.add_argument("--json", dest="json_out", type=Path, help="Optional JSON summary output")
    ap.add_argument("--csv", action="store_true", help="Optional CSV summary output written to <mapfile>.csv")
    ap.add_argument("--markdown", action="store_true", help="Generate a Markdown report instead of HTML")
    ap.add_argument("--top", type=int, default=80, help="Rows to show per table, default: 80")
    ap.add_argument("--min-size", type=int, default=0, help="Ignore contribution rows smaller than this many bytes")
    ap.add_argument(
        "--rom-capacity",
        type=parse_byte_size,
        help="Explicit ROM/non-volatile capacity in bytes. Accepts decimal, hex, or KiB/MiB/GiB suffixes.",
    )
    ap.add_argument(
        "--ram-capacity",
        type=parse_byte_size,
        help="Explicit RAM capacity in bytes. Accepts decimal, hex, or KiB/MiB/GiB suffixes.",
    )
    ap.add_argument(
        "--map-format",
        choices=SUPPORTED_FORMATS,
        default="auto",
        help="Parser profile: auto, generic, gnu, keil/arm, iar, ti, or msvc",
    )
    ap.add_argument(
        "--linker-file",
        type=Path,
        help="Optional linker script/config file used to read memory regions (.ld, .gld, .sct, or .icf)",
    )
    ap.add_argument(
        "--su-dir",
        type=Path,
        help="Optional directory containing GCC .su (and optional .ci) files for stack usage analysis",
    )
    ap.add_argument(
        "--chip-config",
        type=Path,
        help="Optional YAML file defining chip memory regions (replaces map-derived regions)",
    )
    args = ap.parse_args(argv)

    if not args.mapfile.exists():
        print(f"error: mapfile not found: {args.mapfile}", file=sys.stderr)
        return 2
    if args.linker_file and not args.linker_file.exists():
        print(f"error: linker-file not found: {args.linker_file}", file=sys.stderr)
        return 2
    if args.su_dir and not args.su_dir.exists():
        print(f"error: su-dir not found: {args.su_dir}", file=sys.stderr)
        return 2
    if args.chip_config and not args.chip_config.exists():
        print(f"error: chip-config not found: {args.chip_config}", file=sys.stderr)
        return 2

    is_markdown = args.markdown
    map_format = args.map_format
    out_suffix = ".md" if is_markdown else ".html"
    out = args.output or args.mapfile.with_suffix(out_suffix)

    analysis = parse_map(
        args.mapfile,
        min_size=args.min_size,
        map_format=map_format,
        linker_file=args.linker_file,
        su_dir=args.su_dir,
        chip_config=args.chip_config,
    )
    stats = compute_stats(analysis)

    if is_markdown:
        from analyzer.report import render_markdown
        report_content = render_markdown(
            analysis,
            rom_capacity=args.rom_capacity,
            ram_capacity=args.ram_capacity,
        )
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(report_content)
    else:
        report_content = render_html(
            analysis,
            top=args.top,
            rom_capacity=args.rom_capacity,
            ram_capacity=args.ram_capacity,
        )

    out.write_text(report_content, encoding="utf-8")

    if args.json_out:
        args.json_out.write_text(json.dumps(to_jsonable(analysis), indent=2), encoding="utf-8")
    if args.csv:
        csv_out = args.mapfile.with_suffix(".csv")
        module_rows = build_module_rows(stats["by_object"])  # type: ignore[arg-type]
        with csv_out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["table", "rank", "name", "total", "code", "rodata", "data", "bss", "debug", "other", "rom", "ram"])
            for rank, row in enumerate(stats["by_section"], start=1):  # type: ignore[index]
                writer.writerow(
                    [
                        "section",
                        rank,
                        row.get("name", ""),
                        int(row.get("total", 0)),
                        int(row.get("code", 0)),
                        int(row.get("rodata", 0)),
                        int(row.get("data", 0)),
                        int(row.get("bss", 0)),
                        int(row.get("debug", 0)),
                        int(row.get("other", 0)),
                        "",
                        "",
                    ]
                )
            for row in module_rows:
                writer.writerow(
                    [
                        "module",
                        int(row.get("rank", 0)),
                        row.get("name", ""),
                        int(row.get("total", 0)),
                        int(row.get("code", 0)),
                        int(row.get("rodata", 0)),
                        int(row.get("data", 0)),
                        int(row.get("bss", 0)),
                        int(row.get("debug", 0)),
                        int(row.get("other", 0)),
                        int(row.get("rom", 0)),
                        int(row.get("ram", 0)),
                    ]
                )

    print(f"Wrote {out}")
    if args.json_out:
        print(f"Wrote {args.json_out}")
    if args.csv:
        print(f"Wrote {csv_out}")
    if analysis.warnings:
        for warning in analysis.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
