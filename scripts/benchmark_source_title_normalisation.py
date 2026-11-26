#!/usr/bin/env python3
"""Compare the existing source_title columns with composite-key title joins."""
import argparse
import json
import shutil
import sqlite3
import statistics
import time
from pathlib import Path
from sqlite_experiment_common import (backup_database, canonical_hash, capture_metrics,
                                      capture_source_metadata, prepare_database)

TABLES = {
    "page_template_parameters": "parameter_id",
    "page_links": "link_id",
    "candidate_facts": "fact_id",
    "entity_candidates": "entity_candidate_id",
}


def columns(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]


def records(db, table, candidate):
    cols = columns(db, table)
    if not cols:
        raise RuntimeError(f"Missing table: {table}")
    if "source_title" in cols:
        sql = f'SELECT * FROM "{table}"'
    elif candidate:
        fields = ",".join(f't."{c}"' for c in cols)
        sql = (f'SELECT {fields},p.title AS source_title FROM "{table}" t '
               'JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id')
    else:
        raise RuntimeError(f"Baseline missing {table}.source_title")
    cur = db.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def page_keys(db, table):
    return [tuple(r) for r in db.execute(
        f'SELECT DISTINCT dump_id,source_page_id FROM "{table}" '
        'ORDER BY dump_id,source_page_id LIMIT 100')]


def explain(db, table, candidate):
    if candidate:
        sql = (f'SELECT p.title FROM "{table}" t JOIN pages p '
               'ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id '
               'WHERE t.dump_id=? AND t.source_page_id=?')
    else:
        sql = f'SELECT source_title FROM "{table}" WHERE dump_id=? AND source_page_id=?'
    return [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, (1, 1))]


def time_page_lookups(db, table, candidate, keys, repeats):
    if candidate:
        sql = (f'SELECT p.title FROM "{table}" t JOIN pages p '
               'ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id '
               'WHERE t.dump_id=? AND t.source_page_id=?')
    else:
        sql = f'SELECT source_title FROM "{table}" WHERE dump_id=? AND source_page_id=?'
    times, count = [], 0
    for _ in range(repeats):
        start, count = time.perf_counter(), 0
        for key in keys:
            count += len(db.execute(sql, key).fetchall())
        times.append(time.perf_counter() - start)
    return {"keys": len(keys), "rows_per_run": count, "runs_seconds": times,
            "median_seconds": statistics.median(times)}


def time_full_scan(db, table, candidate, repeats):
    if candidate:
        sql = (f'SELECT t.dump_id,t.source_page_id,p.title FROM "{table}" t '
               'JOIN pages p ON p.dump_id=t.dump_id AND p.page_id=t.source_page_id '
               'ORDER BY t.dump_id,t.source_page_id,t.rowid')
    else:
        sql = (f'SELECT dump_id,source_page_id,source_title FROM "{table}" '
               'ORDER BY dump_id,source_page_id,rowid')
    times, count = [], 0
    for _ in range(repeats):
        start = time.perf_counter()
        rows = db.execute(sql).fetchall()
        times.append(time.perf_counter() - start)
        count = len(rows)
    return {"rows": count, "runs_seconds": times, "median_seconds": statistics.median(times)}


def duplicate_titles(db):
    count = db.execute(
        "SELECT COUNT(*) FROM (SELECT title FROM pages GROUP BY title "
        "HAVING COUNT(DISTINCT dump_id)>1)").fetchone()[0]
    examples = [dict(zip(("title", "dump_count", "page_count"), r)) for r in db.execute(
        "SELECT title,COUNT(DISTINCT dump_id),COUNT(*) FROM pages GROUP BY title "
        "HAVING COUNT(DISTINCT dump_id)>1 ORDER BY title LIMIT 100")]
    return count, examples



def duplicate_title_edge_case_test():
    """Prove composite joins handle duplicate titles and unresolved links."""
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE pages(dump_id INTEGER,page_id INTEGER,title TEXT,PRIMARY KEY(dump_id,page_id));
            CREATE TABLE source_rows(dump_id INTEGER,source_page_id INTEGER,source_title TEXT,value TEXT);
            CREATE TABLE page_links(dump_id INTEGER,source_page_id INTEGER,source_title TEXT,destination TEXT,display_text TEXT);
            INSERT INTO pages VALUES (1,7,'Shared title'),(2,7,'Shared title'),(1,8,'Target');
            INSERT INTO source_rows VALUES (1,7,'Shared title','from dump one'),(2,7,'Shared title','from dump two');
            INSERT INTO page_links VALUES
              (1,7,'Shared title','Target','resolved label'),
              (2,7,'Shared title','Missing page','unresolved label');
        """)
        expected_rows = [(1, 7, "Shared title", "from dump one"),
                         (2, 7, "Shared title", "from dump two")]
        rows = db.execute("""SELECT r.dump_id,r.source_page_id,p.title,r.value
            FROM source_rows r JOIN pages p
            ON p.dump_id=r.dump_id AND p.page_id=r.source_page_id
            ORDER BY r.dump_id,r.source_page_id""").fetchall()
        expected_links = [(1, "Target", "resolved label", "Target"),
                          (2, "Missing page", "unresolved label", None)]
        links = db.execute("""SELECT l.dump_id,l.destination,l.display_text,p.title
            FROM page_links l LEFT JOIN pages p
            ON p.dump_id=l.dump_id AND p.title=l.destination
            ORDER BY l.dump_id""").fetchall()
        return {"passed": rows == expected_rows and links == expected_links,
                "duplicate_title_source_rows": rows, "resolved_and_unresolved_links": links}
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--repeats", type=int, default=5)
    a = p.parse_args()
    source, out = a.source.resolve(), a.output_dir.resolve()
    if not source.is_file(): p.error(f"Database not found: {source}")
    if out.exists(): p.error(f"Output directory already exists: {out}")
    if a.repeats < 1: p.error("--repeats must be at least 1")
    out.mkdir(parents=True)
    source_meta = capture_source_metadata(source)
    base_path, cand_path = out / "baseline.sqlite", out / "candidate-no-source-title.sqlite"
    backup_database(source, base_path)
    shutil.copy2(base_path, cand_path)  # exact same snapshot for both arms
    base_prep, cand_prep = prepare_database(base_path), prepare_database(cand_path)
    base, cand = sqlite3.connect(base_path), sqlite3.connect(cand_path)
    try:
        for table in TABLES:
            if "source_title" not in columns(cand, table):
                raise RuntimeError(f"Expected {table}.source_title in source schema")
        duplicate_count, duplicate_examples = duplicate_titles(cand)
        cand.execute("PRAGMA foreign_keys=ON")
        for table in TABLES:
            cand.execute(f'ALTER TABLE "{table}" DROP COLUMN source_title')
        cand.commit()
        cand.execute("VACUUM")
        cand.execute("ANALYZE")
        cand.commit()

        comparisons, fingerprints_pass = {}, True
        for table in TABLES:
            old, new = records(base, table, False), records(cand, table, True)
            old_hash, old_n = canonical_hash(old)
            new_hash, new_n = canonical_hash(new)
            match = old_hash == new_hash and old_n == new_n
            fingerprints_pass &= match
            keys = page_keys(base, table)
            comparisons[table] = {
                "baseline_rows": old_n, "candidate_reconstructed_rows": new_n,
                "baseline_sha256": old_hash, "candidate_sha256": new_hash,
                "logical_records_match": match,
                "baseline_source_page_query_plan": explain(base, table, False),
                "candidate_source_page_query_plan": explain(cand, table, True),
                "baseline_page_lookup": time_page_lookups(base, table, False, keys, a.repeats),
                "candidate_page_join_lookup": time_page_lookups(cand, table, True, keys, a.repeats),
                "baseline_full_reconstruction_scan": time_full_scan(base, table, False, a.repeats),
                "candidate_full_reconstruction_join": time_full_scan(cand, table, True, a.repeats),
            }
        base_metrics, cand_metrics = capture_metrics(base_path), capture_metrics(cand_path)
        schema = {t: {"baseline_has_source_title": "source_title" in columns(base, t),
                      "candidate_has_source_title": "source_title" in columns(cand, t),
                      "candidate_has_dump_and_page_ids": all(x in columns(cand, t) for x in ("dump_id", "source_page_id"))}
                 for t in TABLES}
        schema_pass = all(x["baseline_has_source_title"] and not x["candidate_has_source_title"]
                          and x["candidate_has_dump_and_page_ids"] for x in schema.values())
        base_ok = base_metrics["integrity_check"] == ["ok"] and not base_metrics["foreign_key_errors"]
        cand_ok = cand_metrics["integrity_check"] == ["ok"] and not cand_metrics["foreign_key_errors"]
        edge_case = duplicate_title_edge_case_test()
        passed = fingerprints_pass and schema_pass and base_ok and cand_ok and edge_case["passed"]
        report = {
            "experiment": "source_title_normalisation_prototype", "source_database": str(source),
            "source_opened_read_only": True, "source_modified": False,
            "sqlite_version": sqlite3.sqlite_version, "source_metadata_before_copy": source_meta,
            "identity_rule": "Join on both (dump_id, source_page_id) = pages(dump_id, page_id); never join by title.",
            "preparation": {"baseline": base_prep, "candidate": cand_prep, "candidate_after_schema_change": "VACUUM then ANALYZE"},
            "duplicate_title_cases_total": duplicate_count, "duplicate_title_examples_first_100": duplicate_examples,
            "schema_checks": schema, "table_comparisons": comparisons,
            "duplicate_title_and_unresolved_link_edge_case": edge_case,
            "baseline_metrics": base_metrics, "candidate_metrics": cand_metrics,
            "storage": {
                "baseline_physical_bytes": base_metrics["physical_main_database_bytes"],
                "candidate_physical_bytes": cand_metrics["physical_main_database_bytes"],
                "physical_bytes_saved": base_metrics["physical_main_database_bytes"] - cand_metrics["physical_main_database_bytes"],
                "baseline_allocated_bytes": base_metrics["allocated_page_bytes_excluding_freelist"],
                "candidate_allocated_bytes": cand_metrics["allocated_page_bytes_excluding_freelist"],
                "baseline_logical_payload_bytes": base_metrics["logical_payload_bytes"],
                "candidate_logical_payload_bytes": cand_metrics["logical_payload_bytes"]},
            "validation": {"fingerprints_match": fingerprints_pass, "schema_pass": schema_pass,
                           "baseline_integrity_pass": base_ok, "candidate_integrity_pass": cand_ok,
                           "overall_pass": passed}}
        report_path = out / "comparison.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"SQLite: {sqlite3.sqlite_version}; duplicate titles across dumps: {duplicate_count}")
        for table, result in comparisons.items():
            print(f"{table}: {result['baseline_rows']:,} rows; fingerprint {'PASS' if result['logical_records_match'] else 'FAIL'}")
            print(f"  page lookup baseline/join: {result['baseline_page_lookup']['median_seconds']:.6f}s / {result['candidate_page_join_lookup']['median_seconds']:.6f}s")
            print(f"  full scan baseline/join:  {result['baseline_full_reconstruction_scan']['median_seconds']:.6f}s / {result['candidate_full_reconstruction_join']['median_seconds']:.6f}s")
        print(f"Physical bytes saved: {base_metrics['physical_main_database_bytes'] - cand_metrics['physical_main_database_bytes']:,}")
        print(f"Allocated bytes saved: {base_metrics['allocated_page_bytes_excluding_freelist'] - cand_metrics['allocated_page_bytes_excluding_freelist']:,}")
        print(f"Duplicate-title/unresolved-link edge case: {'PASS' if edge_case['passed'] else 'FAIL'}")
        print(f"Validation: {'PASS' if passed else 'FAIL'}; report: {report_path}")
        return 0 if passed else 1
    finally:
        base.close()
        cand.close()


if __name__ == "__main__":
    raise SystemExit(main())
