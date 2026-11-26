#!/usr/bin/env python3
"""Compare an unchanged SQLite copy with a VACUUM-rebuilt copy.

The source database is opened read-only and is never modified.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__blob_base64__": __import__("base64").b64encode(value).decode("ascii")}
    return value


def table_fingerprint(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    quoted = quote_identifier(table)
    columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    if not columns:
        raise RuntimeError(f"Could not inspect columns for table {table!r}")

    column_count = len(columns)
    order_by = ", ".join(str(index) for index in range(1, column_count + 1))
    cursor = connection.execute(f"SELECT * FROM {quoted} ORDER BY {order_by}")
    digest = hashlib.sha256()
    row_count = 0

    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            encoded = json.dumps(
                [canonical_value(value) for value in row],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            row_count += 1

    return {"rows": row_count, "sha256": digest.hexdigest()}


def inspect_database(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        free_pages = connection.execute("PRAGMA freelist_count").fetchone()[0]
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        fingerprints = {
            table: table_fingerprint(connection, table) for table in tables
        }

        objects: list[dict[str, Any]] | None = None
        dbstat_error: str | None = None
        try:
            objects = [
                {
                    "name": row[0],
                    "object_type": row[1] or "internal",
                    "table_name": row[2] or row[0],
                    "pages": row[3],
                    "allocated_bytes": row[4],
                    "payload_bytes": row[5],
                    "unused_bytes": row[6],
                }
                for row in connection.execute(
                    """
                    SELECT d.name, m.type, m.tbl_name, COUNT(*),
                           COALESCE(SUM(d.pgsize), 0),
                           COALESCE(SUM(d.payload), 0),
                           COALESCE(SUM(d.unused), 0)
                    FROM dbstat AS d
                    LEFT JOIN sqlite_master AS m ON m.name = d.name
                    GROUP BY d.name, m.type, m.tbl_name
                    ORDER BY SUM(d.pgsize) DESC, d.name
                    """
                )
            ]
        except sqlite3.Error as error:
            dbstat_error = str(error)

        return {
            "file_bytes": path.stat().st_size,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_pages": free_pages,
            "integrity_check": integrity,
            "foreign_key_errors": len(foreign_key_errors),
            "foreign_key_error_examples": [list(row) for row in foreign_key_errors[:10]],
            "tables": fingerprints,
            "dbstat_objects": objects,
            "dbstat_error": dbstat_error,
        }
    finally:
        connection.close()


def backup_database(source_path: Path, destination_path: Path) -> None:
    source_uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Existing SQLite database")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory for experiment copies and report")
    args = parser.parse_args()

    source = args.source.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file():
        parser.error(f"Source database does not exist: {source}")
    if output_dir.exists():
        parser.error(f"Output directory already exists; choose a new path: {output_dir}")

    output_dir.mkdir(parents=True)
    baseline_path = output_dir / "baseline-unchanged.sqlite"
    candidate_path = output_dir / "candidate-vacuum.sqlite"
    report_path = output_dir / "comparison.json"

    print(f"Source (read-only): {source}")
    print("Creating independent baseline copy...")
    backup_database(source, baseline_path)
    shutil.copy2(baseline_path, candidate_path)

    print("Inspecting unchanged baseline...")
    baseline = inspect_database(baseline_path)

    print("Running VACUUM on candidate copy...")
    candidate_connection = sqlite3.connect(candidate_path)
    started = time.perf_counter()
    try:
        candidate_connection.execute("VACUUM")
    finally:
        candidate_connection.close()
    vacuum_seconds = time.perf_counter() - started

    print("Inspecting VACUUM candidate...")
    candidate = inspect_database(candidate_path)

    table_names_match = set(baseline["tables"]) == set(candidate["tables"])
    table_hashes_match = table_names_match and all(
        baseline["tables"][name] == candidate["tables"][name]
        for name in baseline["tables"]
    )
    integrity_pass = (
        baseline["integrity_check"] == "ok"
        and candidate["integrity_check"] == "ok"
        and baseline["foreign_key_errors"] == 0
        and candidate["foreign_key_errors"] == 0
    )
    logical_match = table_hashes_match and integrity_pass
    size_change = candidate["file_bytes"] - baseline["file_bytes"]
    reduction_percent = (
        (baseline["file_bytes"] - candidate["file_bytes"])
        / baseline["file_bytes"] * 100
        if baseline["file_bytes"]
        else 0.0
    )

    report = {
        "experiment": "unchanged_vs_vacuum",
        "source_database": str(source),
        "source_was_opened_read_only": True,
        "original_source_modified": False,
        "vacuum_seconds": vacuum_seconds,
        "logical_contents_match": logical_match,
        "table_hashes_match": table_hashes_match,
        "integrity_checks_pass": integrity_pass,
        "baseline": baseline,
        "candidate": candidate,
        "size_comparison": {
            "baseline_bytes": baseline["file_bytes"],
            "candidate_bytes": candidate["file_bytes"],
            "difference_bytes": size_change,
            "reduction_percent": reduction_percent,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print("Comparison summary")
    print("==================")
    print(f"Unchanged copy:       {baseline['file_bytes']:,} bytes")
    print(f"VACUUM candidate:     {candidate['file_bytes']:,} bytes")
    print(f"Size change:          {size_change:+,} bytes")
    print(f"Size reduction:       {reduction_percent:.2f}%")
    print(f"VACUUM elapsed:       {vacuum_seconds:.3f}s")
    print(f"Logical data match:   {'PASS' if table_hashes_match else 'FAIL'}")
    print(f"Integrity checks:     {'PASS' if integrity_pass else 'FAIL'}")
    print(f"JSON report:          {report_path}")
    print(f"Baseline copy:        {baseline_path}")
    print(f"Candidate copy:       {candidate_path}")

    if not logical_match:
        print("ERROR: Candidate does not match the baseline exactly; inspect comparison.json.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
