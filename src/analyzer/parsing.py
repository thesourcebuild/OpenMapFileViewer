from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from .map_formats import PARSERS, get_parser
from .map_formats.base import append_hint
from .linker_formats import parse_linker_file
from .models import Analysis

SUPPORTED_FORMATS = ("auto", "generic", "gnu", "arm", "keil", "iar", "ti", "msvc")


def detect_format(text: str) -> str:
    for parser in PARSERS:
        if parser.can_parse(text):
            return parser.FORMAT_NAME
    return "generic"


def parse_map(
    path: Path,
    min_size: int = 0,
    map_format: str = "auto",
    linker_file: Path | None = None,
    su_dir: Path | None = None,
    chip_config: Path | None = None,
) -> Analysis:
    ext = path.suffix.lower()
    if ext in (".elf", ".axf", ".o"):
        from .elf_parser import parse_elf
        analysis = parse_elf(path, min_size=min_size)
        return _post_process_analysis(analysis, linker_file, su_dir, chip_config)

    return parse_map_text(
        path.read_text(errors="replace"),
        input_file=str(path),
        min_size=min_size,
        map_format=map_format,
        linker_file=linker_file,
        su_dir=su_dir,
        chip_config=chip_config,
    )


def parse_map_text(
    text: str,
    input_file: str = "<memory>",
    min_size: int = 0,
    map_format: str = "auto",
    linker_file: Path | None = None,
    su_dir: Path | None = None,
    chip_config: Path | None = None,
) -> Analysis:
    lines = text.splitlines()
    requested_format = (map_format or "auto").lower()
    detected_format = requested_format if requested_format != "auto" else detect_format(text)
    if detected_format not in SUPPORTED_FORMATS:
        detected_format = "generic"

    analysis = Analysis(
        input_file=input_file,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    analysis.format_hints.append(f"requested={requested_format}")
    analysis.format_hints.append(f"detected={detected_format}")

    for parser in _select_parsers(detected_format):
        parser.parse(lines, analysis, min_size)

    append_hint(analysis, f"profile={detected_format}")
    return _post_process_analysis(analysis, linker_file, su_dir, chip_config)


def _post_process_analysis(
    analysis: Analysis,
    linker_file: Path | None = None,
    su_dir: Path | None = None,
    chip_config: Path | None = None,
) -> Analysis:
    if linker_file is not None:
        linker_path = Path(linker_file)
        linker_format, linker_regions, linker_extras = parse_linker_file(linker_path)
        append_hint(analysis, f"linker={linker_path.name}")
        append_hint(analysis, f"linker-profile={linker_format}")
        analysis.linker_name = linker_path.name
        analysis.linker_format = linker_format
        analysis.linker_content = linker_path.read_text(errors="replace")
        analysis.linker_regions = linker_regions
        analysis.linker_extras = linker_extras
        if linker_regions:
            analysis.memory_regions = linker_regions
        else:
            analysis.warnings.append(f"No memory regions were detected in linker file: {linker_path.name}")


    if chip_config is not None:
        from .chip_info import load_chip_config
        chip_regions = load_chip_config(chip_config)
        if chip_regions:
            analysis.memory_regions = chip_regions
            append_hint(analysis, f"chip-config={chip_config.name}")
        else:
            analysis.warnings.append(f"No memory regions defined in chip config: {chip_config.name}")

    _compute_region_usage(analysis)

    from .validation import detect_layout_issues
    val_warnings, _ = detect_layout_issues(analysis)
    analysis.warnings.extend(val_warnings)

    if su_dir is not None:
        from collections import defaultdict
        from .sua_formats.gcc import parse_sua_dir
        from .utils import source_file as get_source_name
        su_path = Path(su_dir)
        if su_path.exists() and su_path.is_dir():
            analysis.stack_usage = parse_sua_dir(su_path)
            append_hint(analysis, f"stack-usage-dir={su_path.name}")

            symbol_entries = defaultdict(list)
            for entry in analysis.stack_usage:
                symbol_entries[entry.symbol].append(entry)

            for contrib in analysis.contributions:
                if contrib.symbol and contrib.symbol in symbol_entries:
                    entries = symbol_entries[contrib.symbol]
                    matched_entry = None
                    contrib_src_file = get_source_name(contrib.source).lower()
                    for entry in entries:
                        entry_src_file = Path(entry.source_file).name.lower()
                        if entry_src_file == contrib_src_file:
                            matched_entry = entry
                            break
                    if not matched_entry:
                        matched_entry = entries[0]
                    contrib.local_stack = matched_entry.local_size
                    contrib.max_stack = matched_entry.max_depth
        else:
            analysis.warnings.append(f"Stack usage directory does not exist: {su_dir}")

    if not analysis.contributions:
        analysis.warnings.append(
            "No section/object contribution lines were detected. The map format may need a custom parser rule."
        )
    return analysis


def _select_parsers(detected_format: str) -> Sequence:
    if detected_format == "generic":
        return PARSERS
    parser = get_parser(detected_format)
    return (parser,) if parser is not None else PARSERS


def _compute_region_usage(analysis: Analysis) -> None:
    for region in analysis.memory_regions:
        if region.length <= 0:
            continue
        used_ranges: list[tuple[int, int]] = []
        for contribution in analysis.contributions:
            if contribution.address is None or contribution.size <= 0:
                continue
            if region.origin <= contribution.address < region.origin + region.length:
                used_ranges.append(
                    (
                        contribution.address,
                        min(contribution.address + contribution.size, region.origin + region.length),
                    )
                )
        if not used_ranges:
            continue
        used_ranges.sort()
        merged: list[list[int]] = []
        for start, end in used_ranges:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        region.used = sum(end - start for start, end in merged)
