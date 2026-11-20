"""Compare the current Python ingestion/fact extractors with the Rust prototype.

Run from the repository root after building rust-engine in release mode:
    cargo build --release --manifest-path rust-engine/Cargo.toml
    python -m experiments.rust_python_comparison.compare --limit 10000
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import platform
import subprocess
try:
    import resource
except ImportError:  # Windows
    resource = None
import sys
import tempfile
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from time import perf_counter

import mwparserfromhell

from bottom_up.full_pipeline import extract_candidate_facts
from config.paths import get_xml_dump_path
from src.ingestion.xml_reader import inter_page_data

ROOT = Path(__file__).resolve().parents[2]
RUST_BINARY = ROOT / "rust-engine" / "target" / "release" / (
    "tamriel-processing.exe" if os.name == "nt" else "tamriel-processing"
)
REPORT_DIR = ROOT / "data" / "performance"


def peak_rss_mb(who: int = 0):
    """Return process peak RSS in MiB where the platform exposes it."""
    if resource is None:
        return None
    value = resource.getrusage(who).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def write_jsonl(path: Path, rows) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def compare_jsonl(left: Path, right: Path, fields: tuple[str, ...]) -> dict:
    mismatches = []
    count_left = count_right = 0
    with left.open(encoding="utf-8") as a, right.open(encoding="utf-8") as b:
        for index, pair in enumerate(itertools.zip_longest(a, b), start=1):
            left_line, right_line = pair
            if left_line is not None:
                count_left += 1
            if right_line is not None:
                count_right += 1
            if left_line is None or right_line is None:
                mismatches.append({"record": index, "reason": "record_count"})
                break
            left_row = json.loads(left_line)
            right_row = json.loads(right_line)
            if any(left_row.get(field) != right_row.get(field) for field in fields):
                mismatches.append({
                    "record": index,
                    "python": {field: left_row.get(field) for field in fields},
                    "rust": {field: right_row.get(field) for field in fields},
                })
                if len(mismatches) >= 10:
                    break
    return {
        "python_records": count_left,
        "rust_records": count_right,
        "matches": count_left == count_right and not mismatches,
        "mismatches_first_10": mismatches,
    }


def fact_key(fact: dict) -> tuple:
    return (
        int(fact["source_page_id"]),
        fact["source_page"],
        fact["subject"],
        fact["relationship"],
        fact["object"],
        fact["evidence"],
        fact["extraction_method"],
        round(float(fact["confidence"]), 8),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Python against the Rust prototype.")
    parser.add_argument("--limit", type=int, default=10000,
                        help="Maximum number of pages to compare (default: 10000).")
    parser.add_argument("--full", action="store_true",
                        help="Compare the entire dump instead of the default 10000-page sample.")
    parser.add_argument("--fact-pages", type=int, default=1000,
                        help="Number of initial pages used for fact-extraction parity.")
    args = parser.parse_args()
    if args.full and args.limit != 10000:
        parser.error("Use either --full or --limit, not both.")
    if args.full:
        args.limit = None
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive.")
    if args.fact_pages < 1:
        parser.error("--fact-pages must be positive.")
    if not RUST_BINARY.is_file():
        raise SystemExit(
            f"Rust executable not found: {RUST_BINARY}\n"
            "Build it first with: cargo build --release --manifest-path rust-engine/Cargo.toml"
        )

    dump_path = Path(get_xml_dump_path())
    if not dump_path.is_file():
        raise SystemExit(f"Configured XML dump does not exist: {dump_path}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "rust_binary": str(RUST_BINARY),
        "dump_path": str(dump_path),
        "requested_page_limit": args.limit,
    }

    with tempfile.TemporaryDirectory(prefix="tamriel-rust-compare-") as temp:
        temp_dir = Path(temp)
        python_xml = temp_dir / "python_pages.jsonl"
        rust_xml = temp_dir / "rust_pages.jsonl"

        print("1/4 Python XML reader + JSONL output")
        python_rss_before = peak_rss_mb()
        started = perf_counter()
        python_rows = inter_page_data(dump_path)
        if args.limit is not None:
            python_rows = islice(python_rows, args.limit)
        python_count = write_jsonl(python_xml, (
            {
                "page_id": row["page_id"],
                "title": row["title"],
                "namespace": row["namespace"],
                "revision_id": row["revision_id"],
                "text": row["text"],
            }
            for row in python_rows
        ))
        python_xml_seconds = perf_counter() - started
        python_rss_after = peak_rss_mb()

        print("2/4 Rust streaming XML reader + JSONL output")
        rust_child_rss_before = peak_rss_mb(-1)
        command = [str(RUST_BINARY), "xml", str(dump_path)]
        if args.limit is not None:
            command.append(str(args.limit))
        started = perf_counter()
        with rust_xml.open("w", encoding="utf-8") as output:
            result = subprocess.run(command, cwd=ROOT, stdout=output,
                                    stderr=subprocess.PIPE, text=True, check=False)
        rust_xml_seconds = perf_counter() - started
        rust_xml_peak_rss = peak_rss_mb(-1)
        if result.returncode != 0:
            raise RuntimeError(f"Rust XML reader failed:\n{result.stderr}")

        xml_parity = compare_jsonl(
            python_xml, rust_xml,
            ("page_id", "title", "namespace", "revision_id", "text"),
        )
        report["xml"] = {
            "python_elapsed_seconds": python_xml_seconds,
            "rust_elapsed_seconds": rust_xml_seconds,
            "python_pages_per_second": python_count / python_xml_seconds if python_xml_seconds else 0,
            "rust_pages_per_second": xml_parity["rust_records"] / rust_xml_seconds if rust_xml_seconds else 0,
            "speed_ratio_python_over_rust": (
                python_xml_seconds / rust_xml_seconds if rust_xml_seconds else None
            ),
            "python_process_peak_rss_mb_before": python_rss_before,
            "python_process_peak_rss_mb_after": python_rss_after,
            "rust_child_peak_rss_mb_before": rust_child_rss_before,
            "rust_xml_child_peak_rss_mb_after": rust_xml_peak_rss,
            "memory_note": "Peak RSS is process high-water data, not an isolated per-stage allocation measurement.",
            "parity": xml_parity,
        }
        print(f"    Python: {python_xml_seconds:.2f}s ({python_count:,} pages)")
        print(f"    Rust:   {rust_xml_seconds:.2f}s ({xml_parity['rust_records']:,} pages)")
        print(f"    Exact page parity: {xml_parity['matches']}")

        print("3/4 Python fact baseline and plain-text sample")
        fact_input = temp_dir / "fact_pages.jsonl"
        python_facts = []
        fact_pages = 0
        python_wiki_parse_seconds = 0.0
        python_fact_seconds = 0.0
        with python_xml.open(encoding="utf-8") as source, fact_input.open("w", encoding="utf-8") as target:
            for line in source:
                if fact_pages >= args.fact_pages:
                    break
                page = json.loads(line)
                parse_started = perf_counter()
                plain_text = mwparserfromhell.parse(page["text"] or "").strip_code(
                    normalize=True, collapse=True
                )
                python_wiki_parse_seconds += perf_counter() - parse_started
                page_text = {
                    "page_id": int(page["page_id"]),
                    "title": page["title"],
                    "text": plain_text,
                }
                target.write(json.dumps(page_text, ensure_ascii=False) + "\n")
                fact_started = perf_counter()
                python_facts.extend(
                    extract_candidate_facts(
                        plain_text, page_text["page_id"], page_text["title"], provinces=[]
                    )
                )
                python_fact_seconds += perf_counter() - fact_started
                fact_pages += 1
        python_fact_keys = [fact_key(fact) for fact in python_facts]

        print("4/4 Rust fact extraction")
        started = perf_counter()
        rust_result = subprocess.run(
            [str(RUST_BINARY), "facts", str(fact_input)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        rust_fact_seconds = perf_counter() - started
        if rust_result.returncode != 0:
            raise RuntimeError(f"Rust fact extractor failed:\n{rust_result.stderr}")
        rust_facts = [json.loads(line) for line in rust_result.stdout.splitlines() if line.strip()]
        rust_fact_keys = [fact_key(fact) for fact in rust_facts]
        python_set, rust_set = set(python_fact_keys), set(rust_fact_keys)
        fact_parity = {
            "pages_compared": fact_pages,
            "python_facts": len(python_fact_keys),
            "rust_facts": len(rust_fact_keys),
            "matches": python_set == rust_set and len(python_fact_keys) == len(rust_fact_keys),
            "python_only_first_10": [list(item) for item in sorted(python_set - rust_set)[:10]],
            "rust_only_first_10": [list(item) for item in sorted(rust_set - python_set)[:10]],
        }
        report["wiki_parse"] = {
            "python_elapsed_seconds": python_wiki_parse_seconds,
            "pages_compared": fact_pages,
            "scope": "mwparserfromhell parse + strip_code; Rust wikitext parser not implemented yet.",
        }
        report["facts"] = {
            "python_elapsed_seconds": python_fact_seconds,
            "rust_elapsed_seconds": rust_fact_seconds,
            "python_facts_per_second": len(python_facts) / python_fact_seconds if python_fact_seconds else 0,
            "rust_facts_per_second": len(rust_facts) / rust_fact_seconds if rust_fact_seconds else 0,
            "speed_ratio_python_over_rust": (
                python_fact_seconds / rust_fact_seconds if rust_fact_seconds else None
            ),
            "parity": fact_parity,
            "scope": "Three explicit sentence patterns only; province catalogue disabled on both sides.",
        }

    report_path = REPORT_DIR / f"python_rust_comparison_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"Fact parity: {fact_parity['matches']} ({fact_pages:,} pages)")
    print(f"Report: {report_path}")
    return 0 if xml_parity["matches"] and fact_parity["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
