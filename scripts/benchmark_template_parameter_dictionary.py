#!/usr/bin/env python3
"""Compare the current template-parameter table with a lossless dictionary layout.

The source database is opened read-only. The baseline and candidate are independent
copies. The candidate replaces repeated text columns with integer dictionary keys
and exposes the original column layout through a compatibility view.

This is a storage/schema prototype: the Rust writer is not changed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        import base64
        return {"__blob_base64__": base64.b64encode(value).decode("ascii")}
    return value


def table_fingerprint(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    quoted = quote_identifier(table)
    columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    if not columns:
        raise RuntimeError(f"Could not inspect columns for {table!r}")
    order = ", ".join(str(i) for i in range(1, len(columns) + 1))
    cursor = connection.execute(f"SELECT * FROM {quoted} ORDER BY {order}")
    digest = hashlib.sha256()
    count = 0
    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            encoded = json.dumps(
                [canonical_value(value) for value in row],
                ensure_ascii=False, separators=(",", ":"), sort_keys=True,
            ).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def logical_parameter_fingerprint(connection: sqlite3.Connection) -> dict[str, Any]:
    columns = (
        "parameter_id,dump_id,source_page_id,source_title,template_index,"
        "template_name,parameter_index,parameter_name,is_named,parameter_value,"
        "raw_value,evidence_text,extraction_method"
    )
    cursor = connection.execute(
        f"SELECT {columns} FROM page_template_parameters "
        "ORDER BY parameter_id"
    )
    digest = hashlib.sha256()
    count = 0
    while True:
        rows = cursor.fetchmany(1000)
        if not rows:
            break
        for row in rows:
            encoded = json.dumps(
                [canonical_value(value) for value in row],
                ensure_ascii=False, separators=(",", ":"), sort_keys=True,
            ).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def dbstat_summary(connection: sqlite3.Connection) -> dict[str, Any] | None:
    try:
        rows = connection.execute(
            "SELECT d.name, COALESCE(m.type,'internal'), "
            "COALESCE(m.tbl_name,d.name), SUM(d.pgsize), "
            "SUM(d.payload), SUM(d.unused) "
            "FROM dbstat d LEFT JOIN sqlite_master m ON m.name=d.name "
            "GROUP BY d.name,m.type,m.tbl_name ORDER BY SUM(d.pgsize) DESC"
        ).fetchall()
    except sqlite3.Error:
        return None
    return {
        "objects": [
            {"name": r[0], "type": r[1], "table": r[2],
             "allocated_bytes": r[3], "payload_bytes": r[4], "unused_bytes": r[5]}
            for r in rows
        ],
        "allocated_bytes": sum(r[3] for r in rows),
        "payload_bytes": sum(r[4] for r in rows),
        "unused_bytes": sum(r[5] for r in rows),
    }


def inspect(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        return {
            "file_bytes": path.stat().st_size,
            "page_size": connection.execute("PRAGMA page_size").fetchone()[0],
            "page_count": connection.execute("PRAGMA page_count").fetchone()[0],
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "parameter_logical": logical_parameter_fingerprint(connection),
            "dbstat": dbstat_summary(connection),
        }
    finally:
        connection.close()


def backup(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def build_dictionary_candidate(path: Path) -> float:
    connection = sqlite3.connect(path)
    started = time.perf_counter()
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        required = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='page_template_parameters'"
        ).fetchone()
        if not required:
            raise RuntimeError("page_template_parameters table is missing")
        expected = connection.execute(
            "SELECT COUNT(*) FROM page_template_parameters"
        ).fetchone()[0]

        connection.execute("""
            CREATE TABLE template_name_dictionary (
                template_name_id INTEGER PRIMARY KEY,
                value TEXT NOT NULL UNIQUE
            );
            CREATE TABLE parameter_name_dictionary (
                parameter_name_id INTEGER PRIMARY KEY,
                value TEXT NOT NULL UNIQUE
            );
            CREATE TABLE parameter_value_dictionary (
                parameter_value_id INTEGER PRIMARY KEY,
                value TEXT NOT NULL UNIQUE
            );
            CREATE TABLE source_title_dictionary (
                source_title_id INTEGER PRIMARY KEY,
                value TEXT NOT NULL UNIQUE
            );
        """)
        for dictionary, column in (
            ("template_name_dictionary", "template_name"),
            ("parameter_name_dictionary", "parameter_name"),
            ("parameter_value_dictionary", "parameter_value"),
            ("source_title_dictionary", "source_title"),
        ):
            connection.execute(
                f"INSERT INTO {dictionary}(value) "
                f"SELECT DISTINCT {column} FROM page_template_parameters"
            )

        connection.execute("""
            CREATE TABLE page_template_parameters_dictionary (
                parameter_id INTEGER PRIMARY KEY,
                dump_id INTEGER NOT NULL,
                source_page_id INTEGER NOT NULL,
                source_title_id INTEGER NOT NULL,
                template_index INTEGER NOT NULL,
                template_name_id INTEGER NOT NULL,
                parameter_index INTEGER NOT NULL,
                parameter_name_id INTEGER NOT NULL,
                is_named INTEGER NOT NULL,
                parameter_value_id INTEGER NOT NULL,
                raw_value TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                extraction_method TEXT NOT NULL,
                FOREIGN KEY (dump_id,source_page_id)
                    REFERENCES pages(dump_id,page_id) ON DELETE CASCADE,
                FOREIGN KEY (source_title_id)
                    REFERENCES source_title_dictionary(source_title_id),
                FOREIGN KEY (template_name_id)
                    REFERENCES template_name_dictionary(template_name_id),
                FOREIGN KEY (parameter_name_id)
                    REFERENCES parameter_name_dictionary(parameter_name_id),
                FOREIGN KEY (parameter_value_id)
                    REFERENCES parameter_value_dictionary(parameter_value_id)
            )
        """)
        connection.execute("""
            INSERT INTO page_template_parameters_dictionary
            SELECT p.parameter_id,p.dump_id,p.source_page_id,st.source_title_id,
                   p.template_index,tn.template_name_id,p.parameter_index,
                   pn.parameter_name_id,p.is_named,pv.parameter_value_id,
                   p.raw_value,p.evidence_text,p.extraction_method
            FROM page_template_parameters p
            JOIN source_title_dictionary st ON st.value=p.source_title
            JOIN template_name_dictionary tn ON tn.value=p.template_name
            JOIN parameter_name_dictionary pn ON pn.value=p.parameter_name
            JOIN parameter_value_dictionary pv ON pv.value=p.parameter_value
        """)
        actual = connection.execute(
            "SELECT COUNT(*) FROM page_template_parameters_dictionary"
        ).fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"Row count changed during conversion: {expected} -> {actual}")

        connection.execute("""
            CREATE INDEX idx_template_parameters_lookup_dictionary
                ON page_template_parameters_dictionary(template_name_id,parameter_name_id);
            CREATE INDEX idx_template_parameter_name_value_dictionary
                ON page_template_parameters_dictionary(parameter_name_id,parameter_value_id);
            CREATE INDEX idx_template_parameters_source_dictionary
                ON page_template_parameters_dictionary(dump_id,source_page_id)
        """)
        connection.execute("DROP TABLE page_template_parameters")
        connection.execute("""
            ALTER TABLE page_template_parameters_dictionary
            RENAME TO page_template_parameters_dictionary
        """)
        # Preserve the original read/query shape through a view with the same name.
        connection.execute("""
            CREATE VIEW page_template_parameters AS
            SELECT p.parameter_id,p.dump_id,p.source_page_id,st.value AS source_title,
                   p.template_index,tn.value AS template_name,p.parameter_index,
                   pn.value AS parameter_name,p.is_named,pv.value AS parameter_value,
                   p.raw_value,p.evidence_text,p.extraction_method
            FROM page_template_parameters_dictionary p
            JOIN source_title_dictionary st ON st.source_title_id=p.source_title_id
            JOIN template_name_dictionary tn ON tn.template_name_id=p.template_name_id
            JOIN parameter_name_dictionary pn ON pn.parameter_name_id=p.parameter_name_id
            JOIN parameter_value_dictionary pv ON pv.parameter_value_id=p.parameter_value_id
        """)
        connection.execute("COMMIT")
        connection.execute("VACUUM")
        return time.perf_counter() - started
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output_dir.resolve()
    if not source.is_file():
        parser.error(f"Source database does not exist: {source}")
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    output.mkdir(parents=True)
    baseline_path = output / "baseline-unchanged.sqlite"
    candidate_path = output / "candidate-dictionary.sqlite"
    report_path = output / "comparison.json"

    print(f"Source (read-only): {source}")
    backup(source, baseline_path)
    shutil.copy2(baseline_path, candidate_path)
    print("Inspecting unchanged baseline...")
    baseline = inspect(baseline_path)
    print("Building dictionary candidate...")
    conversion_seconds = build_dictionary_candidate(candidate_path)
    print("Inspecting candidate...")
    candidate = inspect(candidate_path)

    # Compare every unaffected user table, plus the reconstructed parameter rows.
    base = sqlite3.connect(f"file:{baseline_path.as_posix()}?mode=ro", uri=True)
    cand = sqlite3.connect(f"file:{candidate_path.as_posix()}?mode=ro", uri=True)
    try:
        base_tables = {
            row[0] for row in base.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        } - {"page_template_parameters"}
        cand_tables = {
            row[0] for row in cand.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        } - {
            "page_template_parameters", "page_template_parameters_dictionary", "template_name_dictionary",
            "parameter_name_dictionary", "parameter_value_dictionary",
            "source_title_dictionary",
        }
        unaffected_match = base_tables == cand_tables and all(
            table_fingerprint(base, name) == table_fingerprint(cand, name)
            for name in base_tables
        )
        baseline_parameter = logical_parameter_fingerprint(base)
        candidate_parameter = logical_parameter_fingerprint(cand)
        parameter_match = baseline_parameter == candidate_parameter
    finally:
        base.close()
        cand.close()

    integrity_pass = (
        baseline["integrity_check"] == "ok"
        and candidate["integrity_check"] == "ok"
        and baseline["foreign_key_errors"] == 0
        and candidate["foreign_key_errors"] == 0
    )
    logical_match = unaffected_match and parameter_match and integrity_pass
    saved = baseline["file_bytes"] - candidate["file_bytes"]
    reduction = saved / baseline["file_bytes"] * 100 if baseline["file_bytes"] else 0.0
    report = {
        "experiment": "template_parameter_dictionary",
        "source_database": str(source),
        "source_opened_read_only": True,
        "original_source_modified": False,
        "candidate_design": {
            "dictionary_columns": [
                "template_name", "parameter_name", "parameter_value", "source_title"
            ],
            "preserved_verbatim_columns": [
                "raw_value", "evidence_text", "extraction_method"
            ],
            "compatibility_view": "page_template_parameters_compat",
            "note": "Read-only schema prototype; Rust write path is not migrated.",
        },
        "conversion_seconds_including_vacuum": conversion_seconds,
        "logical_contents_match": logical_match,
        "unaffected_tables_match": unaffected_match,
        "template_parameter_logical_match": parameter_match,
        "integrity_checks_pass": integrity_pass,
        "baseline": baseline,
        "candidate": candidate,
        "size_comparison": {
            "baseline_bytes": baseline["file_bytes"],
            "candidate_bytes": candidate["file_bytes"],
            "bytes_saved": saved,
            "reduction_percent": reduction,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print()
    print("Dictionary schema comparison")
    print("============================")
    print(f"Unchanged copy:       {baseline['file_bytes']:,} bytes")
    print(f"Dictionary candidate:{candidate['file_bytes']:>12,} bytes")
    print(f"Space saved:          {saved:+,} bytes")
    print(f"Size reduction:       {reduction:.2f}%")
    print(f"Conversion + VACUUM:  {conversion_seconds:.3f}s")
    print(f"Other tables match:   {'PASS' if unaffected_match else 'FAIL'}")
    print(f"Parameter rows match: {'PASS' if parameter_match else 'FAIL'}")
    print(f"Integrity checks:     {'PASS' if integrity_pass else 'FAIL'}")
    print(f"Logical data match:   {'PASS' if logical_match else 'FAIL'}")
    print(f"JSON report:          {report_path}")
    print(f"Baseline copy:        {baseline_path}")
    print(f"Candidate copy:       {candidate_path}")
    return 0 if logical_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
