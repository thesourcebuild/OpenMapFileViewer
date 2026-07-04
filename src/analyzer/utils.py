from __future__ import annotations

import os
import re

from .section_rules import SECTION_RULES, REGION_KIND_RULES

SIZE_SUFFIXES = {
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "mib": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
}


def parse_int(token: str, default_base: int = 10) -> int:
    token = token.strip().rstrip(",")
    if not token:
        result = 0
    elif token.lower().startswith("0x"):
        result = int(token, 16)
    elif token.lower().endswith("h"):
        result = int(token[:-1], 16)
    elif re.fullmatch(r"[0-9A-Fa-f]+", token) and any(c in token for c in "ABCDEFabcdef"):
        result = int(token, 16)
    else:
        result = int(token, default_base)
    return result


def parse_byte_size(token: str) -> int:
    token = token.strip()
    if not token:
        raise ValueError("size cannot be empty")
    match = re.fullmatch(r"(?i)\s*(0x[0-9a-f]+|\d+)\s*([kmg](?:ib|b)?|)\s*", token)
    if not match:
        raise ValueError(f"invalid size: {token!r}")
    value = parse_int(match.group(1))
    multiplier = SIZE_SUFFIXES.get(match.group(2).lower(), 1)
    return value * multiplier


def nice_size(n: int) -> str:
    n = int(n or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n < 1024:
        result = f"{sign}{n} B"
    elif n < 1024 * 1024:
        result = f"{sign}{n / 1024:.2f} KiB"
    else:
        result = f"{sign}{n / (1024 * 1024):.2f} MiB"
    return result


def section_class(section: str) -> str:
    s = (section or "").strip()
    sl = s.lower()
    compact = sl.replace(" ", "")

    # Try keyword matching first
    for category, keywords in SECTION_RULES["keywords"].items():
        if compact in keywords:
            return category

    # Try prefix matching
    for name, prefixes in SECTION_RULES["prefixes"]:
        if any(sl == prefix.lower() or sl.startswith(prefix.lower()) for prefix in prefixes):
            return name

    # Try suffix matching
    for name, suffixes in SECTION_RULES["suffixes"]:
        if any(sl.endswith(suffix) for suffix in suffixes):
            return name

    return "other"


def normalize_source(src: str) -> str:
    if not src:
        result = "<unknown>"
    else:
        src = src.strip()
        src = re.sub(r"\s+", " ", src)
        src = src.split(" #", 1)[0].strip()
        if src.startswith("*fill*") or src in {"LOAD", "START", "END", "PROVIDE"}:
            result = "<linker/generated>"
        else:
            result = src or "<unknown>"
    return result


def object_name(source: str) -> str:
    source = normalize_source(source)
    match = re.search(r"([^\s/\\]+\.(?:o|obj))(?:\b|\))", source, re.I)
    if match:
        result = match.group(1)
    else:
        match = re.search(r"([^/\\\s]+\.(?:a|lib))\(([^)]+)\)", source, re.I)
        if match:
            result = f"{match.group(1)}({match.group(2)})"
        else:
            result = os.path.basename(source)
    return result


def archive_name(source: str) -> str:
    source = normalize_source(source)
    match = re.search(r"([^/\\\s]+\.(?:a|lib))\(([^)]+)\)", source, re.I)
    if match:
        result = match.group(1)
    else:
        match = re.search(r"([^/\\\s]+\.(?:a|lib))\b", source, re.I)
        if match:
            result = match.group(1)
        else:
            result = "<not in archive>"
    return result


def source_file(source: str) -> str:
    base = object_name(source)
    return re.sub(r"\.(?:o|obj)\)?$", ".c", base, flags=re.I)


def region_kind(name: str, attrs: str = "", origin: int = 0, length: int = 0) -> str:
    lowered = (name or "").lower()

    # Check keyword matching
    for kind, rules in REGION_KIND_RULES.items():
        if any(t in lowered for t in rules["keywords"]):
            return kind

    # Check attribute matching
    attrs_lower = (attrs or "").lower()
    if "w" in attrs_lower:
        return "ram"
    elif "!" in attrs_lower:
        parts = attrs_lower.split("!", 1)
        if len(parts) > 1 and ("r" in parts[1] or "x" in parts[1]):
            return "ram"
    elif "x" in attrs_lower or "r" in attrs_lower:
        return "flash"

    return "other"

