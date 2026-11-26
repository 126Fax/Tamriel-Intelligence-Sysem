#!/usr/bin/env python3
"""Audit Rust source for ai_pages references and possible indirect SQL sites.

This is a static review aid, not a complete Rust parser. It reports direct
references and separately flags SQL construction/query execution sites for
manual inspection, including format!/concat!, macros and query builders.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIRECT = re.compile(r"ai_pages", re.IGNORECASE)
DYNAMIC = re.compile(
    r"\b(format!|concat!|include_str!|macro_rules!|sqlx::query|query_as|query_scalar|QueryBuilder|query_builder|sea_query|diesel::|sql!)|"
    r"\.prepare(?:_cached)?\s*\(|\.query(?:_row|_map)?\s*\(|\.execute\s*\(|"
    r"execute_batch\s*\()",
    re.IGNORECASE,
)
SQL_WORDS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|JOIN|CREATE TABLE|ALTER TABLE)\b", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    root = args.root.resolve()
    source_dirs = [root / "rust-version" / "src", root / "rust-engine" / "src"]
    files = sorted({path for directory in source_dirs if directory.exists() for path in directory.rglob("*.rs")})
    direct, dynamic = [], []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            relative = path.relative_to(root).as_posix()
            if DIRECT.search(line):
                direct.append({"file": relative, "line": number, "text": line.strip()})
            if DYNAMIC.search(line) and (SQL_WORDS.search(line) or any(
                token in line for token in ("prepare", "query", "execute", "format!", "concat!", "macro_rules!", "QueryBuilder", "sea_query", "diesel::", "sql!")
            )):
                dynamic.append({"file": relative, "line": number, "text": line.strip()})
    report = {
        "audit": "ai_pages_rust_usage",
        "root": str(root),
        "rust_files_scanned": len(files),
        "direct_ai_pages_references": direct,
        "possible_dynamic_sql_or_query_sites_for_manual_review": dynamic,
        "interpretation": "Direct references identify explicit ai_pages use. Dynamic/query sites are candidates for manual inspection; they are not proof of ai_pages access.",
        "direct_reference_files": sorted({item["file"] for item in direct}),
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(f"Rust files scanned: {len(files)}")
    print(f"Direct ai_pages references: {len(direct)}")
    for item in direct:
        print(f"  {item['file']}:{item['line']}: {item['text']}")
    print(f"Potential dynamic SQL/query sites for manual review: {len(dynamic)}")
    for item in dynamic:
        print(f"  {item['file']}:{item['line']}: {item['text']}")
    if args.output:
        print(f"JSON report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
