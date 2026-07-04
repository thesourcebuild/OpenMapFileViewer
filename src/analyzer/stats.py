from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Callable, Dict, Iterable, List

from .models import Analysis, Contribution
from .utils import archive_name, object_name, section_class, source_file


def aggregate(contribs: Iterable[Contribution], key_func: Callable[[Contribution], str]) -> List[Dict[str, object]]:
    totals: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for contribution in contribs:
        key = key_func(contribution)
        totals[key]["total"] += contribution.size
        totals[key][contribution.kind or section_class(contribution.section)] += contribution.size

    rows = [{"name": name, **parts} for name, parts in totals.items()]
    rows.sort(key=lambda row: int(row.get("total", 0)), reverse=True)
    return rows


def compute_stats(analysis: Analysis) -> Dict[str, object]:
    all_contribs = [
        contribution
        for contribution in analysis.contributions
        if contribution.size > 0 and contribution.source != "<region total>"
    ]
    section_total_rows = [contribution for contribution in all_contribs if contribution.source == "<section total>"]
    # Detect if the parser contributed per-object summary lines (e.g. Keil "Image component sizes").
    # When present, exclude individual symbol entries to avoid double-counting.
    # Restrict this to Keil, IAR, or ARM parser profiles to avoid breaking other formats.
    is_keil_or_iar = any(
        "profile=keil" in hint or "profile=iar" in hint or "profile=arm" in hint
        for hint in analysis.format_hints
    )
    has_object_totals = is_keil_or_iar and any(
        not contribution.symbol
        and contribution.source not in {"<section total>", "<region total>"}
        for contribution in all_contribs
    )
    leaf_rows = [
        contribution
        for contribution in all_contribs
        if contribution.source not in {"<section total>", "<region total>"}
        and not (has_object_totals and contribution.symbol)
    ]
    summary_rows = section_total_rows if section_total_rows else leaf_rows

    by_class = aggregate(summary_rows, lambda contribution: contribution.kind or section_class(contribution.section))
    by_section = aggregate(summary_rows, lambda contribution: contribution.section)
    by_object = aggregate(leaf_rows, lambda contribution: object_name(contribution.source))
    by_archive = aggregate(leaf_rows, lambda contribution: archive_name(contribution.source))
    by_source = aggregate(leaf_rows, lambda contribution: source_file(contribution.source))
    symbols = sorted(
        [contribution for contribution in all_contribs if contribution.symbol and contribution.size > 0],
        key=lambda contribution: contribution.size,
        reverse=True,
    )
    files = {object_name(contribution.source) for contribution in leaf_rows}
    total = sum(contribution.size for contribution in summary_rows)

    return {
        "total_bytes": total,
        "by_class": by_class,
        "by_section": by_section,
        "by_object": by_object,
        "by_archive": by_archive,
        "by_source": by_source,
        "symbols": symbols,
        "object_count": len(files),
        "section_count": len({contribution.section for contribution in all_contribs}),
        "contribution_count": len(all_contribs),
    }


def build_module_rows(by_object: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    module_rows: List[Dict[str, object]] = []
    for index, row in enumerate(by_object, start=1):
        enriched = dict(row)
        enriched["rank"] = index
        enriched["rom"] = int(row.get("code", 0)) + int(row.get("rodata", 0)) + int(row.get("data", 0))
        enriched["ram"] = int(row.get("data", 0)) + int(row.get("bss", 0))
        enriched["total"] = enriched["rom"] + int(row.get("bss", 0))
        module_rows.append(enriched)
    return module_rows


def to_jsonable(analysis: Analysis) -> Dict[str, object]:
    data = asdict(analysis)
    stats = compute_stats(analysis)
    data["stats"] = {
        key: [asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in value]
        if isinstance(value, list)
        else value
        for key, value in stats.items()
    }
    return data
