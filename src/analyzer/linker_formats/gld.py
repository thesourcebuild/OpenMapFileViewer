from __future__ import annotations

import re
from typing import Sequence

from ..models import MemoryRegion
from . import gnu

FORMAT_NAME = "gld"
SUFFIXES = (".gld",)

# Regex to match preprocessor directives
_DIRECTIVE_RE = re.compile(r"^\s*#\s*(?P<directive>if|ifdef|ifndef|elif|else|endif|define|undef)\b(?P<args>.*)$")

# Regex to extract macros
_DEFINE_RE = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)(?:\s+(?P<val>.*))?$")
_UNDEF_RE = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*$")

# Regex to match defined(...)
_DEFINED_PAREN_RE = re.compile(r"\bdefined\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*\)")
_DEFINED_BARE_RE = re.compile(r"\bdefined\s+(?P<name>[A-Za-z_]\w*)")

# Regex to match hex literals
_HEX_RE = re.compile(r"\b0[xX][0-9A-Fa-f]+\b")

# Regex to match identifiers
_IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")


def can_parse(text: str) -> bool:
    sample = text[:5_000_000].lower()
    return "memory" in sample and ("origin" in sample or "length" in sample)


def eval_condition(expr: str, defines: dict[str, str]) -> bool:
    """Evaluate C preprocessor condition expression safely."""
    # 1. Clean up and resolve defined(MACRO) or defined MACRO
    expr = _DEFINED_PAREN_RE.sub(lambda m: "1" if m.group("name") in defines else "0", expr)
    expr = _DEFINED_BARE_RE.sub(lambda m: "1" if m.group("name") in defines else "0", expr)

    # 2. Replace C-style logical operators with Python-style logical operators
    expr = expr.replace("&&", " and ")
    expr = expr.replace("||", " or ")
    expr = expr.replace("!", " not ")
    expr = expr.replace("==", " == ")
    expr = expr.replace("!=", " != ")
    expr = expr.replace(">=", " >= ")
    expr = expr.replace("<=", " <= ")

    # 3. Replace all hex literals with decimal string representations
    expr = _HEX_RE.sub(lambda m: str(int(m.group(0), 16)), expr)

    # 4. Resolve identifiers
    def replace_ident(match):
        word = match.group(0)
        if word in ("and", "or", "not"):
            return word
        if word in defines:
            val = defines[word].strip()
            if not val:
                return "1"
            if _HEX_RE.match(val):
                return str(int(val, 16))
            if val.isdigit():
                return val
            return val
        return "0"

    expr = _IDENT_RE.sub(replace_ident, expr)

    # 5. Clean up spaces and validate using safe character whitelist
    expr = expr.strip()
    safe_pattern = re.compile(r"^(?:[0-9\s()+\-*/%<>=!&|]|and\b|or\b|not\b|True\b|False\b)+$")
    if not safe_pattern.match(expr):
        return False

    try:
        # Evaluate in a restricted scope
        return bool(eval(expr, {"__builtins__": {}}))
    except Exception:
        return False


def preprocess(lines: Sequence[str]) -> list[str]:
    # Strip multiline comments first
    full_text = "\n".join(lines)
    full_text = re.sub(r"/\*.*?\*/", "", full_text, flags=re.DOTALL)
    
    clean_lines = []
    for raw_line in full_text.splitlines():
        # Strip single-line comments
        line = re.sub(r"//.*$", "", raw_line)
        clean_lines.append(line)

    defines: dict[str, str] = {}
    stack = []
    out_lines = []

    def is_active() -> bool:
        return all(level["current_active"] for level in stack)

    for line in clean_lines:
        # Match preprocessor directive
        m = _DIRECTIVE_RE.match(line)
        if m:
            directive = m.group("directive")
            args = m.group("args").strip()

            if directive == "define":
                if is_active():
                    dm = _DEFINE_RE.match(args)
                    if dm:
                        name = dm.group("name")
                        val = dm.group("val") or "1"
                        defines[name] = val
                continue
            elif directive == "undef":
                if is_active():
                    um = _UNDEF_RE.match(args)
                    if um:
                        name = um.group("name")
                        defines.pop(name, None)
                continue
            elif directive in ("if", "ifdef", "ifndef"):
                parent_active = is_active()
                cond = False
                if parent_active:
                    if directive == "ifdef":
                        cond = args in defines
                    elif directive == "ifndef":
                        cond = args not in defines
                    else:  # if
                        cond = eval_condition(args, defines)
                current_active = parent_active and cond
                branch_taken = current_active
                stack.append({
                    "parent_active": parent_active,
                    "branch_taken": branch_taken,
                    "current_active": current_active,
                })
                continue
            elif directive == "elif":
                if not stack:
                    continue
                level = stack[-1]
                if level["parent_active"] and not level["branch_taken"]:
                    cond = eval_condition(args, defines)
                    level["current_active"] = cond
                    level["branch_taken"] = cond
                else:
                    level["current_active"] = False
                continue
            elif directive == "else":
                if not stack:
                    continue
                level = stack[-1]
                if level["parent_active"] and not level["branch_taken"]:
                    level["current_active"] = True
                    level["branch_taken"] = True
                else:
                    level["current_active"] = False
                continue
            elif directive == "endif":
                if stack:
                    stack.pop()
                continue

        # If we are in an active preprocessor block, keep the line
        if is_active():
            out_lines.append(line)

    return out_lines


def parse(lines: Sequence[str]) -> tuple[list[MemoryRegion], dict]:
    preprocessed_lines = preprocess(lines)
    return gnu.parse(preprocessed_lines)
