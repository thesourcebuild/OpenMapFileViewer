from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..models import StackUsageEntry


def parse_su_line(line: str) -> dict | None:
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    loc_func = parts[0]
    size_str = parts[1]
    qualifier = parts[2]

    # Find colons. Ignore index 1 on Windows if it is part of a drive letter (e.g. C:\)
    colon_indices = []
    for i, c in enumerate(loc_func):
        if c == ":":
            if i == 1 and len(loc_func) > 2 and loc_func[2] in {"/", "\\"}:
                continue
            colon_indices.append(i)

    if len(colon_indices) < 3:
        return None

    idx3 = colon_indices[-3]
    idx2 = colon_indices[-2]
    idx1 = colon_indices[-1]

    file_path = loc_func[:idx3]
    try:
        line_num = int(loc_func[idx3 + 1 : idx2])
        col_num = int(loc_func[idx2 + 1 : idx1])
        func_name = loc_func[idx1 + 1 :]
        size_val = int(size_str)
    except ValueError:
        return None

    return {
        "file": file_path,
        "line": line_num,
        "col": col_num,
        "func": func_name,
        "size": size_val,
        "qualifier": qualifier,
    }


def parse_su_file(path: Path) -> List[dict]:
    entries = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            res = parse_su_line(line)
            if res:
                entries.append(res)
    except Exception:
        pass
    return entries


def parse_ci_file(path: Path) -> List[Tuple[str, str]]:
    edges = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        edge_matches = re.finditer(r"edge:\s*\{([^}]+)\}", content, re.DOTALL)
        for match in edge_matches:
            body = match.group(1)
            source_match = re.search(r"sourcename:\s*(?:\"([^\"]+)\"|'([^']+)'|(\S+))", body)
            target_match = re.search(r"targetname:\s*(?:\"([^\"]+)\"|'([^']+)'|(\S+))", body)
            if source_match and target_match:
                src = source_match.group(1) or source_match.group(2) or source_match.group(3)
                tgt = target_match.group(1) or target_match.group(2) or target_match.group(3)
                edges.append((src.strip(), tgt.strip()))
    except Exception:
        pass
    return edges


def parse_sua_dir(su_dir: Path) -> List[StackUsageEntry]:
    # 1. Find all .su and .ci files recursively
    su_files = list(su_dir.rglob("*.su"))
    ci_files = list(su_dir.rglob("*.ci"))

    # 2. Parse all .su files
    local_stacks: Dict[str, int] = {}
    entry_details: Dict[str, dict] = {}

    for su_file in su_files:
        for entry in parse_su_file(su_file):
            func = entry["func"]
            size = entry["size"]
            if func not in local_stacks or size > local_stacks[func]:
                local_stacks[func] = size
                entry_details[func] = entry

    # 3. Parse all .ci files to build the call graph
    graph: Dict[str, Set[str]] = {}
    for ci_file in ci_files:
        for caller, callee in parse_ci_file(ci_file):
            if caller not in graph:
                graph[caller] = set()
            graph[caller].add(callee)

    # 4. Compute max stack depth using DFS + cycle detection + memoization
    memo: Dict[str, int] = {}

    def get_max_depth(func: str, visited: Set[str]) -> int:
        if func in memo:
            return memo[func]
        if func in visited:
            # Cycle/recursion detected: return 0 to break cycle
            return 0

        visited.add(func)
        local_size = local_stacks.get(func, 0)

        callees = graph.get(func, set())
        max_callee_depth = 0
        for callee in callees:
            depth = get_max_depth(callee, visited)
            if depth > max_callee_depth:
                max_callee_depth = depth

        visited.remove(func)
        total_depth = local_size + max_callee_depth
        memo[func] = total_depth
        return total_depth

    # Calculate for all functions
    stack_entries: List[StackUsageEntry] = []
    for func in local_stacks:
        max_depth = get_max_depth(func, set())
        details = entry_details[func]
        stack_entries.append(
            StackUsageEntry(
                symbol=func,
                local_size=details["size"],
                max_depth=max_depth,
                source_file=details["file"],
                line=details["line"],
                qualifier=details["qualifier"],
            )
        )

    return stack_entries
