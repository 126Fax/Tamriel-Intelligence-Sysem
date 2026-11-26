#!/usr/bin/env python3
"""Audit SQLite storage and compare source-title normalisation without touching the source.

Creates an independent, VACUUMed/ANALYZEd baseline and a candidate that removes
four duplicated source_title columns. Read compatibility views reconstruct the
original logical rows through the composite (dump_id, source_page_id) key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

SOURCE_TABLES = {
    "page_template_parameters": {
        "physical": "page_template_parameters_normalised",
        "key": "parameter_id",
        "columns": [
            "parameter_id", "dump_id", "source_page_id", "source_title",
            "template_index", "template_name", "parameter_index", "parameter_name",
            "is_named", "parameter_value", "raw_value", "evidence_text",
            "extraction_method",
        ],
        "storage_columns": [
            "parameter_id", "dump_id", "source_page_id", "template_index",
            "template_name", "parameter_index", "parameter_name", "is_named",
            "parameter_value", "raw_value", "evidence_text", "extraction_method",
        ],
        "create": """CREATE TABLE page_template_parameters_normalised (
            parameter_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL, template_index INTEGER NOT NULL,
            template_name TEXT NOT NULL, parameter_index INTEGER NOT NULL,
            parameter_name TEXT NOT NULL, is_named INTEGER NOT NULL,
            parameter_value TEXT NOT NULL, raw_value TEXT NOT NULL,
            evidence_text TEXT NOT NULL, extraction_method TEXT NOT NULL,
            FOREIGN KEY (dump_id,source_page_id)
              REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
        )""",
        "indexes": [
            "CREATE INDEX idx_template_parameters_lookup ON page_template_parameters_normalised(template_name,parameter_name)",
            "CREATE INDEX idx_template_parameter_name_value ON page_template_parameters_normalised(parameter_name COLLATE NOCASE,parameter_value COLLATE NOCASE)",
            "CREATE INDEX idx_template_parameters_source ON page_template_parameters_normalised(dump_id,source_page_id)",
        ],
        "select": """SELECT t.parameter_id,t.dump_id,t.source_page_id,p.title AS source_title,
            t.template_index,t.template_name,t.parameter_index,t.parameter_name,
            t.is_named,t.parameter_value,t.raw_value,t.evidence_text,t.extraction_method
            FROM page_template_parameters_normalised t
            JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id""",
    },
    "page_links": {
        "physical": "page_links_normalised",
        "key": "link_id",
        "columns": ["link_id", "dump_id", "source_page_id", "source_title", "destination", "display_text"],
        "storage_columns": ["link_id", "dump_id", "source_page_id", "destination", "display_text"],
        "create": """CREATE TABLE page_links_normalised (
            link_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL, destination TEXT NOT NULL,
            display_text TEXT NOT NULL,
            FOREIGN KEY (dump_id,source_page_id)
              REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
        )""",
        "indexes": [
            "CREATE INDEX idx_page_links_destination ON page_links_normalised(destination)",
            "CREATE INDEX idx_page_links_source ON page_links_normalised(dump_id,source_page_id)",
        ],
        "select": """SELECT t.link_id,t.dump_id,t.source_page_id,p.title AS source_title,
            t.destination,t.display_text
            FROM page_links_normalised t
            JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id""",
    },
    "candidate_facts": {
        "physical": "candidate_facts_normalised",
        "key": "fact_id",
        "columns": ["fact_id", "dump_id", "source_page_id", "source_title", "subject", "relationship", "object", "evidence_text", "extraction_method", "confidence"],
        "storage_columns": ["fact_id", "dump_id", "source_page_id", "subject", "relationship", "object", "evidence_text", "extraction_method", "confidence"],
        "create": """CREATE TABLE candidate_facts_normalised (
            fact_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL, subject TEXT NOT NULL,
            relationship TEXT NOT NULL, object TEXT NOT NULL,
            evidence_text TEXT NOT NULL, extraction_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            FOREIGN KEY (dump_id,source_page_id)
              REFERENCES pages(dump_id,page_id) ON DELETE CASCADE,
            UNIQUE(dump_id,source_page_id,subject,relationship,object,evidence_text)
        )""",
        "indexes": [
            "CREATE INDEX idx_candidate_facts_lookup ON candidate_facts_normalised(relationship,subject,object)",
        ],
        "select": """SELECT t.fact_id,t.dump_id,t.source_page_id,p.title AS source_title,
            t.subject,t.relationship,t.object,t.evidence_text,t.extraction_method,t.confidence
            FROM candidate_facts_normalised t
            JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id""",
    },
    "entity_candidates": {
        "physical": "entity_candidates_normalised",
        "key": "entity_candidate_id",
        "columns": ["entity_candidate_id", "dump_id", "source_page_id", "source_title", "entity_type", "value", "evidence_text", "extraction_method", "source_type", "source_id", "mod_id"],
        "storage_columns": ["entity_candidate_id", "dump_id", "source_page_id", "entity_type", "value", "evidence_text", "extraction_method", "source_type", "source_id", "mod_id"],
        "create": """CREATE TABLE entity_candidates_normalised (
            entity_candidate_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL, entity_type TEXT NOT NULL
              CHECK(entity_type IN ('race','occupation','book')),
            value TEXT NOT NULL, evidence_text TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'uesp'
              CHECK(source_type IN ('uesp','user','mod')),
            source_id TEXT NOT NULL, mod_id TEXT,
            FOREIGN KEY (dump_id,source_page_id)
              REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
        )""",
        "indexes": [
            "CREATE INDEX idx_entity_candidates_type_value ON entity_candidates_normalised(entity_type,value COLLATE NOCASE)",
            "CREATE INDEX idx_entity_candidates_source ON entity_candidates_normalised(source_type,source_id,mod_id)",
        ],
        "select": """SELECT t.entity_candidate_id,t.dump_id,t.source_page_id,p.title AS source_title,
            t.entity_type,t.value,t.evidence_text,t.extraction_method,t.source_type,t.source_id,t.mod_id
            FROM entity_candidates_normalised t
            JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id""",
    },
}


def qid(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        import base64
        return {"blob_base64": base64.b64encode(value).decode("ascii")}
    return value


def fingerprint_rows(connection: sqlite3.Connection, sql: str, order_by: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    cursor = connection.execute(f"{sql} ORDER BY {order_by}")
    while True:
        batch = cursor.fetchmany(1000)
        if not batch:
            break
        for row in batch:
            encoded = json.dumps([canonical(v) for v in row], ensure_ascii=False,
                                 separators=(",", ":"), sort_keys=True).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def table_fingerprint(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    info = connection.execute(f"PRAGMA table_info({qid(table)})").fetchall()
    columns = [row[1] for row in info]
    if not columns:
        raise RuntimeError(f"Missing table {table!r}")
    # Ordering every column is deterministic even for tables without a declared PK.
    order = ",".join(str(i + 1) for i in range(len(columns)))
    return fingerprint_rows(connection, f"SELECT * FROM {qid(table)}", order)


def file_inventory(path: Path) -> dict[str, int]:
    result = {}
    for label, candidate in (
        ("main", path), ("wal", Path(str(path) + "-wal")),
        ("shm", Path(str(path) + "-shm")),
    ):
        result[label] = candidate.stat().st_size if candidate.exists() else 0
    result["total_sidecars_bytes"] = result["wal"] + result["shm"]
    result["physical_total_bytes"] = result["main"] + result["wal"] + result["shm"]
    return result


def dbstat(connection: sqlite3.Connection) -> dict[str, Any] | None:
    try:
        rows = connection.execute("""
            SELECT d.name,COALESCE(m.type,'internal'),SUM(d.pgsize),
                   SUM(d.payload),SUM(d.unused)
            FROM dbstat d LEFT JOIN sqlite_master m ON m.name=d.name
            GROUP BY d.name,m.type ORDER BY SUM(d.pgsize) DESC,d.name
        """).fetchall()
    except sqlite3.Error:
        return None
    return {
        "objects": [
            {"name": r[0], "type": r[1], "allocated_bytes": r[2],
             "payload_bytes": r[3], "unused_bytes": r[4]} for r in rows
        ],
        "allocated_bytes": sum(r[2] for r in rows),
        "payload_bytes": sum(r[3] for r in rows),
        "unused_bytes": sum(r[4] for r in rows),
    }


def inspect_database(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        pragma = lambda name: connection.execute(f"PRAGMA {name}").fetchone()[0]
        version = connection.execute("SELECT sqlite_version()").fetchone()[0]
        page_size, page_count, free_count = (
            int(pragma("page_size")), int(pragma("page_count")), int(pragma("freelist_count"))
        )
        objects = dbstat(connection)
        return {
            "sqlite_version": version,
            "journal_mode": pragma("journal_mode"),
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": free_count,
            "physical_files": file_inventory(path),
            "allocated_live_pages_bytes": (page_count - free_count) * page_size,
            "allocated_all_pages_bytes": page_count * page_size,
            "freelist_bytes": free_count * page_size,
            "dbstat": objects,
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        connection.close()


def backup_read_only(source: Path, destination: Path) -> None:
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def compact_and_analyse(path: Path) -> float:
    connection = sqlite3.connect(path)
    started = time.perf_counter()
    try:
        # Use the same rollback-journal mode for all experiment copies.
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
    finally:
        connection.close()
    return time.perf_counter() - started


def migrate_remove_source_titles(path: Path) -> float:
    connection = sqlite3.connect(path)
    started = time.perf_counter()
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        for logical_name, spec in SOURCE_TABLES.items():
            columns = {row[1] for row in connection.execute(
                f"PRAGMA table_info({qid(logical_name)})"
            )}
            if not columns:
                raise RuntimeError(f"Required table {logical_name!r} is missing")
            if "source_title" not in columns:
                raise RuntimeError(f"{logical_name} has no source_title column; wrong source schema?")
            old_count = connection.execute(
                f"SELECT COUNT(*) FROM {qid(logical_name)}"
            ).fetchone()[0]
            for index in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (logical_name,),
            ).fetchall():
                connection.execute(f"DROP INDEX {qid(index[0])}")
            connection.execute(
                f"ALTER TABLE {qid(logical_name)} RENAME TO {qid(spec['physical'] + '_old')}"
            )
            connection.execute(spec["create"])
            old_name = qid(spec["physical"] + "_old")
            new_cols = ",".join(qid(c) for c in spec["storage_columns"])
            connection.execute(
                f"INSERT INTO {qid(spec['physical'])} ({new_cols}) "
                f"SELECT {new_cols} FROM {old_name}"
            )
            new_count = connection.execute(
                f"SELECT COUNT(*) FROM {qid(spec['physical'])}"
            ).fetchone()[0]
            if old_count != new_count:
                raise RuntimeError(f"{logical_name} row count changed: {old_count} -> {new_count}")
            connection.execute(f"DROP TABLE {old_name}")
            for index_sql in spec["indexes"]:
                connection.execute(index_sql)
            # Keep the old read interface. The source title is reconstructed using
            # both dump_id and source_page_id, never by title-only matching.
            select_columns = ",".join(
                f"t.{qid(c)}" if c != "source_title" else "p.title AS source_title"
                for c in spec["columns"]
            )
            connection.execute(
                f"CREATE VIEW {qid(logical_name)} AS SELECT {select_columns} "
                f"FROM {qid(spec['physical'])} t JOIN pages p "
                "ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id"
            )
        connection.commit()
        return time.perf_counter() - started
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def logical_checks(baseline: sqlite3.Connection, candidate: sqlite3.Connection) -> dict[str, Any]:
    source_hashes = {}
    for name, spec in SOURCE_TABLES.items():
        order = spec["key"]
        left = fingerprint_rows(baseline, f"SELECT * FROM {qid(name)}", order)
        right = fingerprint_rows(candidate, f"SELECT * FROM {qid(name)}", order)
        source_hashes[name] = {"baseline": left, "candidate": right, "match": left == right}

    base_tables = {
        row[0] for row in baseline.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    candidate_tables = {
        row[0] for row in candidate.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    unaffected = sorted(base_tables - set(SOURCE_TABLES))
    unaffected_checks = {}
    for table in unaffected:
        left, right = table_fingerprint(baseline, table), table_fingerprint(candidate, table)
        unaffected_checks[table] = {"match": left == right, "baseline": left, "candidate": right}

    # Explicit application-shaped reconstruction checks.
    behavioural = {}
    queries = {
        "source_title_lookup": (
            """SELECT t.dump_id,t.source_page_id,t.source_title
               FROM page_template_parameters t""",
            "1,2,3",
        ),
        "fact_retrieval": (
            """SELECT fact_id,dump_id,source_page_id,source_title,subject,relationship,
                      object,evidence_text,extraction_method,confidence FROM candidate_facts""",
            "1",
        ),
        "link_traversal": (
            """SELECT l.link_id,l.dump_id,l.source_page_id,l.source_title,
                      l.destination,l.display_text,p.title AS resolved_destination
               FROM page_links l
               LEFT JOIN pages p ON p.dump_id=l.dump_id AND p.title=l.destination""",
            "1",
        ),
    }
    for name, (sql, order) in queries.items():
        left, right = fingerprint_rows(baseline, sql, order), fingerprint_rows(candidate, sql, order)
        behavioural[name] = {"match": left == right, "baseline": left, "candidate": right}

    return {
        "logical_source_tables": source_hashes,
        "unaffected_tables": unaffected_checks,
        "behavioural_queries": behavioural,
        "all_logical_checks_match": (
            all(v["match"] for v in source_hashes.values())
            and all(v["match"] for v in unaffected_checks.values())
            and all(v["match"] for v in behavioural.values())
        ),
    }


def query_performance(connection: sqlite3.Connection, label: str) -> dict[str, Any]:
    # Choose a real source key from the largest source table, if available.
    row = connection.execute(
        "SELECT dump_id,source_page_id FROM page_template_parameters ORDER BY parameter_id LIMIT 1"
    ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT dump_id,page_id FROM pages ORDER BY dump_id,page_id LIMIT 1"
        ).fetchone()
    if row is None:
        return {"label": label, "skipped": "database has no source pages"}
    dump_id, page_id = row
    query = """SELECT f.fact_id,f.subject,f.relationship,f.object,f.evidence_text,
                      p.title AS source_title
               FROM candidate_facts f
               JOIN pages p ON p.dump_id=f.dump_id AND p.page_id=f.source_page_id
               WHERE f.dump_id=? AND f.source_page_id=?
               ORDER BY f.fact_id"""
    plan = [list(r) for r in connection.execute("EXPLAIN QUERY PLAN " + query, (dump_id, page_id))]
    timings = []
    for _ in range(7):
        started = time.perf_counter()
        connection.execute(query, (dump_id, page_id)).fetchall()
        timings.append(time.perf_counter() - started)
    return {
        "label": label, "test_key": {"dump_id": dump_id, "page_id": page_id},
        "explain_query_plan": plan, "runs_seconds": timings,
        "median_seconds": statistics.median(timings),
    }


def ai_pages_audit(root: Path) -> dict[str, Any]:
    source_root = root / "rust-version" / "src"
    direct = []
    dynamic_indicators = []
    if not source_root.is_dir():
        return {"error": f"Rust source directory not found: {source_root}"}
    for path in sorted(source_root.rglob("*.rs")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, 1):
            if "ai_pages" in line:
                direct.append({"file": str(path.relative_to(root)), "line": number,
                               "text": line.strip()[:300]})
            if re.search(r"\b(format!|query_as|query_builder|prepare_cached|prepare)\b", line):
                dynamic_indicators.append({"file": str(path.relative_to(root)), "line": number,
                                           "text": line.strip()[:220]})
    return {
        "direct_ai_pages_references": direct,
        "sql_construction_review_points": dynamic_indicators,
        "note": "Static source scan. Review SQL construction points manually; dynamically assembled identifiers may not contain the literal table name.",
        "direct_reference_count": len(direct),
        "sql_construction_indicator_count": len(dynamic_indicators),
    }


def duplicate_title_edge_case_test() -> dict[str, Any]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
            CREATE TABLE source_dumps(dump_id INTEGER PRIMARY KEY,source_name TEXT NOT NULL);
            CREATE TABLE pages(
                dump_id INTEGER NOT NULL,page_id INTEGER NOT NULL,title TEXT NOT NULL,
                namespace_id INTEGER NOT NULL,namespace_name TEXT NOT NULL,
                revision_id INTEGER,text_length INTEGER NOT NULL,page_text TEXT NOT NULL,
                PRIMARY KEY(dump_id,page_id),
                FOREIGN KEY(dump_id) REFERENCES source_dumps(dump_id));
            CREATE TABLE page_links(link_id INTEGER PRIMARY KEY,dump_id INTEGER NOT NULL,
                source_page_id INTEGER NOT NULL,source_title TEXT NOT NULL,
                destination TEXT NOT NULL,display_text TEXT NOT NULL,
                FOREIGN KEY(dump_id,source_page_id) REFERENCES pages(dump_id,page_id));
            CREATE INDEX idx_page_links_destination ON page_links(destination);
            CREATE INDEX idx_page_links_source ON page_links(dump_id,source_page_id);
            INSERT INTO source_dumps VALUES(1,'dump-one'),(2,'dump-two');
            INSERT INTO pages VALUES
                (1,10,'Shared title',0,'Main',1,5,'first'),
                (2,10,'Shared title',0,'Main',2,6,'second'),
                (1,11,'Target',0,'Main',3,1,'x');
            INSERT INTO page_links VALUES
                (1,1,10,'Shared title','Target','first target'),
                (2,2,10,'Shared title','Missing page','unresolved text');
        """)
        # Apply the same composite-key reconstruction principle to the link table.
        connection.execute("ALTER TABLE page_links RENAME TO page_links_old")
        connection.execute("""CREATE TABLE page_links_normalised(
            link_id INTEGER PRIMARY KEY,dump_id INTEGER NOT NULL,source_page_id INTEGER NOT NULL,
            destination TEXT NOT NULL,display_text TEXT NOT NULL,
            FOREIGN KEY(dump_id,source_page_id) REFERENCES pages(dump_id,page_id))""")
        connection.execute("""INSERT INTO page_links_normalised
            SELECT link_id,dump_id,source_page_id,destination,display_text FROM page_links_old""")
        connection.execute("DROP TABLE page_links_old")
        connection.execute("CREATE INDEX idx_page_links_destination ON page_links_normalised(destination)")
        connection.execute("CREATE INDEX idx_page_links_source ON page_links_normalised(dump_id,source_page_id)")
        connection.execute("""CREATE VIEW page_links AS
            SELECT l.link_id,l.dump_id,l.source_page_id,p.title AS source_title,
                   l.destination,l.display_text
            FROM page_links_normalised l JOIN pages p
            ON p.dump_id=l.dump_id AND p.page_id=l.source_page_id""")
        rows = connection.execute(
            "SELECT dump_id,source_title,destination,display_text FROM page_links ORDER BY link_id"
        ).fetchall()
        expected = [
            (1, "Shared title", "Target", "first target"),
            (2, "Shared title", "Missing page", "unresolved text"),
        ]
        # Also prove title resolution is dump-scoped and the unresolved text survives.
        resolved = connection.execute("""
            SELECT l.dump_id,l.destination,p.page_text
            FROM page_links l LEFT JOIN pages p
              ON p.dump_id=l.dump_id AND p.title=l.destination
            ORDER BY l.link_id
        """).fetchall()
        passed = rows == expected and resolved == [(1, "Target", "x"), (2, "Missing page", None)]
        return {"passed": passed, "duplicate_title_rows": rows,
                "dump_scoped_link_resolution": resolved}
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="Existing Rust SQLite database (opened read-only)")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New output directory; must not already exist")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output_dir.resolve()
    if not source.is_file():
        parser.error(f"Source database does not exist: {source}")
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    output.mkdir(parents=True)

    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        required = {r[0] for r in source_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        missing = sorted({"pages", *SOURCE_TABLES} - required)
        if missing:
            parser.error("Source database is missing required tables: " + ", ".join(missing))
    finally:
        source_connection.close()

    source_metadata = inspect_database(source)
    baseline_path = output / "baseline.sqlite"
    candidate_path = output / "candidate-source-title-normalised.sqlite"
    backup_read_only(source, baseline_path)
    baseline_maintenance_seconds = compact_and_analyse(baseline_path)
    shutil.copy2(baseline_path, candidate_path)
    candidate_migration_seconds = migrate_remove_source_titles(candidate_path)
    candidate_maintenance_seconds = compact_and_analyse(candidate_path)

    baseline = inspect_database(baseline_path)
    candidate = inspect_database(candidate_path)
    base_conn = sqlite3.connect(f"file:{baseline_path.as_posix()}?mode=ro", uri=True)
    cand_conn = sqlite3.connect(f"file:{candidate_path.as_posix()}?mode=ro", uri=True)
    try:
        checks = logical_checks(base_conn, cand_conn)
        performance = {
            "baseline": query_performance(base_conn, "baseline"),
            "candidate": query_performance(cand_conn, "candidate"),
        }
        query_plans = {
            "source_title_lookup": {
                "baseline": [list(r) for r in base_conn.execute(
                    "EXPLAIN QUERY PLAN SELECT t.source_title FROM page_template_parameters t WHERE t.dump_id=? AND t.source_page_id=?",
                    (1, 1))],
                "candidate": [list(r) for r in cand_conn.execute(
                    "EXPLAIN QUERY PLAN SELECT t.source_title FROM page_template_parameters t WHERE t.dump_id=? AND t.source_page_id=?",
                    (1, 1))],
            }
        }
    finally:
        base_conn.close()
        cand_conn.close()

    source_titles_removed = {}
    for logical, spec in SOURCE_TABLES.items():
        c = sqlite3.connect(f"file:{candidate_path.as_posix()}?mode=ro", uri=True)
        try:
            source_titles_removed[logical] = {
                "physical_table": spec["physical"],
                "source_title_column_removed": "source_title" not in {
                    r[1] for r in c.execute(f"PRAGMA table_info({qid(spec['physical'])})")
                },
                "compatibility_view_exists": c.execute(
                    "SELECT type FROM sqlite_master WHERE name=?", (logical,)
                ).fetchone() == ("view",),
            }
        finally:
            c.close()

    edge_case = duplicate_title_edge_case_test()
    integrity_pass = (
        baseline["integrity_check"] == "ok" and candidate["integrity_check"] == "ok"
        and baseline["foreign_key_errors"] == 0 and candidate["foreign_key_errors"] == 0
    )
    schema_pass = all(v["source_title_column_removed"] and v["compatibility_view_exists"]
                      for v in source_titles_removed.values())
    passed = checks["all_logical_checks_match"] and integrity_pass and schema_pass and edge_case["passed"]
    size_saved = baseline["physical_files"]["physical_total_bytes"] - candidate["physical_files"]["physical_total_bytes"]
    report = {
        "experiment": "source_title_normalisation",
        "source_database": str(source),
        "source_opened_read_only": True,
        "original_source_modified": False,
        "source_configuration_before_copy": source_metadata,
        "maintenance": {
            "baseline_vacuum_then_analyze_seconds": baseline_maintenance_seconds,
            "candidate_vacuum_then_analyze_seconds": candidate_maintenance_seconds,
            "candidate_schema_migration_seconds": candidate_migration_seconds,
            "sequence": ["VACUUM", "ANALYZE", "capture query plans", "benchmark"],
        },
        "baseline": baseline,
        "candidate": candidate,
        "size_comparison": {
            "baseline_physical_bytes_including_sidecars": baseline["physical_files"]["physical_total_bytes"],
            "candidate_physical_bytes_including_sidecars": candidate["physical_files"]["physical_total_bytes"],
            "bytes_saved": size_saved,
            "reduction_percent": (size_saved / baseline["physical_files"]["physical_total_bytes"] * 100)
                if baseline["physical_files"]["physical_total_bytes"] else 0.0,
        },
        "source_title_columns": source_titles_removed,
        "logical_and_behavioural_validation": checks,
        "query_performance": performance,
        "query_plans": query_plans,
        "duplicate_title_and_unresolved_link_edge_case": edge_case,
        "ai_pages_static_audit": ai_pages_audit(Path(__file__).resolve().parents[1]),
        "integrity_checks_pass": integrity_pass,
        "all_acceptance_checks_pass": passed,
        "notes": [
            "This is an isolated schema prototype. Rust production writers and readers are not migrated.",
            "Compatibility views preserve SELECT access to the original logical columns; views are not writable.",
            "All source-title reconstruction joins use both dump_id and source_page_id.",
            "The source database is opened read-only; all maintenance and migration occurs on independent copies.",
            "The query-plan example key (1,1) may not exist in the source; the timed query uses an actual key.",
            "SQLite dbstat payload is B-tree payload, not a compressed logical-text estimate.",
        ],
    }
    report_path = output / "comparison.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nSource-title normalisation experiment")
    print("=====================================")
    print(f"Source (read-only): {source}")
    print(f"SQLite version: {source_metadata['sqlite_version']}")
    print(f"Baseline physical size:  {baseline['physical_files']['physical_total_bytes']:,} bytes")
    print(f"Candidate physical size: {candidate['physical_files']['physical_total_bytes']:,} bytes")
    print(f"Space saved: {size_saved:+,} bytes ({report['size_comparison']['reduction_percent']:.2f}%)")
    print(f"Baseline VACUUM + ANALYZE: {baseline_maintenance_seconds:.3f}s")
    print(f"Candidate migration:       {candidate_migration_seconds:.3f}s")
    print(f"Candidate VACUUM + ANALYZE:{candidate_maintenance_seconds:>10.3f}s")
    print(f"Logical/behavioural checks: {'PASS' if checks['all_logical_checks_match'] else 'FAIL'}")
    print(f"Duplicate-title edge case: {'PASS' if edge_case['passed'] else 'FAIL'}")
    print(f"SQLite/FK integrity:       {'PASS' if integrity_pass else 'FAIL'}")
    print(f"All acceptance checks:     {'PASS' if passed else 'FAIL'}")
    print(f"Report: {report_path}")
    print(f"Baseline copy: {baseline_path}")
    print(f"Candidate copy: {candidate_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
