#!/usr/bin/env python3
"""Utility to pretty-print and diff Max patcher JSON files.

Usage:
    python maxpat_diff.py <file.amxd|file.maxpat>
    python maxpat_diff.py <file_a> <file_b>

Max for Live .amxd and .maxpat files are JSON. This script formats them
for readable terminal output and optionally diffs two versions.
"""

import json
import sys
import difflib


def load_patcher(path: str) -> dict:
    """Load and parse a Max patcher JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summarize_patcher(data: dict) -> str:
    """Return a human-readable summary of a Max patcher."""
    patcher = data.get("patcher", data)
    boxes = patcher.get("boxes", [])
    lines = patcher.get("lines", [])

    object_counts: dict[str, int] = {}
    for box in boxes:
        obj = box.get("box", {})
        maxclass = obj.get("maxclass", "unknown")
        object_counts[maxclass] = object_counts.get(maxclass, 0) + 1

    summary_lines = [
        f"Objects: {len(boxes)}",
        f"Connections: {len(lines)}",
        "",
        "Object types:",
    ]
    for cls, count in sorted(object_counts.items(), key=lambda x: -x[1]):
        summary_lines.append(f"  {cls}: {count}")

    return "\n".join(summary_lines)


def pretty_json(data: dict) -> str:
    """Return indented JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def diff_files(path_a: str, path_b: str) -> str:
    """Return a unified diff between two patcher files."""
    a = pretty_json(load_patcher(path_a)).splitlines(keepends=True)
    b = pretty_json(load_patcher(path_b)).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=path_a, tofile=path_b))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if len(sys.argv) == 2:
        data = load_patcher(sys.argv[1])
        print(f"--- {sys.argv[1]} ---\n")
        print(summarize_patcher(data))
        print("\n--- Full JSON ---\n")
        print(pretty_json(data))
    elif len(sys.argv) == 3:
        result = diff_files(sys.argv[1], sys.argv[2])
        if result:
            print(result)
        else:
            print("No differences found.")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
