from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .models import MemoryRegion
from .utils import parse_byte_size


def _safe_eval(expr: str) -> int:
    """Evaluate a safe arithmetic expression with hex/dec numbers, +, -, *, /, //, %, and parens."""
    expr = expr.strip()

    byte_match = re.fullmatch(r"(?i)\s*(0x[0-9a-f]+|\d+)\s*([kmg](?:ib|b)?)\s*", expr)
    if byte_match:
        return parse_byte_size(expr)

    hex_dec_match = re.fullmatch(r"(?i)\s*(0x[0-9a-f]+|\d+)\s*", expr)
    if hex_dec_match:
        return int(hex_dec_match.group(1), 0)

    tokens = _tokenize(expr)
    if not tokens:
        raise ValueError(f"empty expression: {expr!r}")
    result, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise ValueError(f"unexpected tokens after position {pos} in {expr!r}")
    return result


_TOKEN_RE = re.compile(r"""(?x)
    \s+ |
    (?P<hex>0x[0-9a-fA-F]+) |
    (?P<dec>\d+) |
    (?P<op>[+\-*/%()])
""")


def _tokenize(expr: str) -> List[str]:
    tokens: List[str] = []
    for m in _TOKEN_RE.finditer(expr):
        if m.group("hex"):
            tokens.append(str(int(m.group("hex"), 16)))
        elif m.group("dec"):
            tokens.append(m.group("dec"))
        elif m.group("op"):
            tokens.append(m.group("op"))
    return tokens


def _parse_expr(tokens: List[str], pos: int):
    return _parse_addsub(tokens, pos)


def _parse_addsub(tokens: List[str], pos: int):
    val, pos = _parse_muldiv(tokens, pos)
    while pos < len(tokens) and tokens[pos] in ("+", "-"):
        op = tokens[pos]
        rhs, pos = _parse_muldiv(tokens, pos + 1)
        if op == "+":
            val += rhs
        else:
            val -= rhs
    return val, pos


def _parse_muldiv(tokens: List[str], pos: int):
    val, pos = _parse_primary(tokens, pos)
    while pos < len(tokens) and tokens[pos] in ("*", "/", "//", "%"):
        op = tokens[pos]
        rhs, pos = _parse_primary(tokens, pos + 1)
        if op == "*":
            val *= rhs
        elif op == "/":
            val //= rhs
        elif op == "//":
            val //= rhs
        else:
            val %= rhs
    return val, pos


def _parse_primary(tokens: List[str], pos: int):
    if pos >= len(tokens):
        raise ValueError("unexpected end of expression")
    tok = tokens[pos]
    if tok == "(":
        val, pos = _parse_expr(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ValueError("missing closing parenthesis")
        return val, pos + 1
    if tok.isdigit() or (tok.startswith("-") and tok[1:].isdigit()):
        return int(tok), pos + 1
    raise ValueError(f"unexpected token: {tok!r}")


def _resolve_number(value: Any) -> int:
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        raise ValueError("empty number")
    return _safe_eval(s)


def _infer_kind(name: str, explicit_kind: str) -> str:
    if explicit_kind:
        return explicit_kind.strip().lower()
    name_upper = name.upper().replace(" ", "_").replace("-", "_")
    if any(kw in name_upper for kw in ("DRAM", "IRAM", "SRAM", "RAM", "RTC")):
        return "ram"
    if any(kw in name_upper for kw in ("CACHE", "FLASH", "ROM")):
        return "flash"
    return ""


def _load_schema_a(data: Dict[str, Any]) -> List[MemoryRegion]:
    """Schema A: memory_regions list with name/origin/length/kind/attrs."""
    raw = data.get("memory_regions")
    if not isinstance(raw, list):
        raise ValueError("Schema A requires 'memory_regions' list")
    result: List[MemoryRegion] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"memory_regions[{i}] is not a mapping")
        name = entry.get("name")
        if not name:
            raise ValueError(f"memory_regions[{i}] is missing 'name'")
        if "origin" not in entry:
            raise ValueError(f"memory_regions[{i}] ('{name}') is missing 'origin'")
        if "length" not in entry:
            raise ValueError(f"memory_regions[{i}] ('{name}') is missing 'length'")
        result.append(MemoryRegion(
            name=str(name),
            origin=_resolve_number(entry["origin"]),
            length=_resolve_number(entry["length"]),
            attrs=str(entry.get("attrs", "")).strip(),
            kind=_infer_kind(str(name), entry.get("kind", "")),
        ))
    return result


def _load_schema_b(data: Dict[str, Any]) -> List[MemoryRegion]:
    """Schema B: ESP-IDF-style flat dict with primary_address/length/secondary_address/name/kind."""
    result: List[MemoryRegion] = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Schema B entry {key!r} is not a mapping")
        if "primary_address" not in entry:
            raise ValueError(f"Schema B entry {key!r} is missing 'primary_address'")
        if "length" not in entry:
            raise ValueError(f"Schema B entry {key!r} is missing 'length'")

        name = str(entry.get("name", key))
        origin = _resolve_number(entry["primary_address"])
        length = _resolve_number(entry["length"])
        kind = _infer_kind(name, entry.get("kind", ""))

        result.append(MemoryRegion(
            name=name,
            origin=origin,
            length=length,
            attrs=str(entry.get("attrs", "")).strip(),
            kind=kind,
        ))

        if "secondary_address" in entry:
            result.append(MemoryRegion(
                name=name + "_alias",
                origin=_resolve_number(entry["secondary_address"]),
                length=length,
                attrs=str(entry.get("attrs", "")).strip(),
                kind=kind,
            ))
    return result


def _load_schema_c(data: Dict[str, Any]) -> List[MemoryRegion]:
    """Schema C: regions list with name/base or origin/size or length/type or kind."""
    raw = data.get("regions")
    if not isinstance(raw, list):
        raise ValueError("Schema C requires 'regions' list")
    result: List[MemoryRegion] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"regions[{i}] is not a mapping")
        name = entry.get("name")
        if not name:
            raise ValueError(f"regions[{i}] is missing 'name'")
        origin_raw = entry.get("origin") if "origin" in entry else entry.get("base")
        if origin_raw is None:
            raise ValueError(f"regions[{i}] ('{name}') is missing 'origin' or 'base'")
        length_raw = entry.get("length") if "length" in entry else entry.get("size")
        if length_raw is None:
            raise ValueError(f"regions[{i}] ('{name}') is missing 'length' or 'size'")
        kind_raw = entry.get("kind") if "kind" in entry else entry.get("type", "")
        result.append(MemoryRegion(
            name=str(name),
            origin=_resolve_number(origin_raw),
            length=_resolve_number(length_raw),
            attrs=str(entry.get("attrs", "")).strip(),
            kind=_infer_kind(str(name), kind_raw),
        ))
    return result


def load_chip_config(path: Path) -> List[MemoryRegion]:
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required to load chip config files. "
            "Install it with: pip install PyYAML>=6.0"
        )

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("YAML chip config must be a mapping at the top level")

    if "memory_regions" in data:
        return _load_schema_a(data)

    if "regions" in data:
        return _load_schema_c(data)

    first_val = next(iter(data.values()), None)
    if isinstance(first_val, dict) and "primary_address" in first_val:
        return _load_schema_b(data)

    raise ValueError(
        "Unrecognized YAML format. Supported schemas:\n"
        "  Schema A: top-level 'memory_regions' list\n"
        "  Schema B: ESP-IDF-style (keys with 'primary_address')\n"
        "  Schema C: top-level 'regions' list"
    )
