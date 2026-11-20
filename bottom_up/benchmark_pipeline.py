"""Benchmark Bottom-Up analysis on isolated, evenly spaced page samples.

Run from the repository root:
    python -m bottom_up.benchmark_pipeline
    python -m bottom_up.benchmark_pipeline --sizes 100 1000 10000
"""
import argparse
import sqlite3
import tempfile
from pathlib import Path
from time import perf_counter

from src.database import database
from bottom_up.full_pipeline import analyse_dump, build_knowledge_base


def get_source_dump():
    connection = database.get_connection()
    try:
        row = connection.execute(
            "SELECT dump_id, source_name FROM source_dumps "
            "ORDER BY dump_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("No imported dump found. Import the UESP dump first.")
        count = connection.execute(
            "SELECT COUNT(*) FROM pages WHERE dump_id = ?", (row["dump_id"],)
        ).fetchone()[0]
        return row["dump_id"], row["source_name"], count
    finally:
        connection.close()


def copy_evenly_spaced_pages(source_database_path, source_dump_id, sample_size, scratch_connection):
    """Copy a deterministic sample spread across the source page-ID range."""
    source_connection = sqlite3.connect(source_database_path)
    source_connection.row_factory = sqlite3.Row
    try:
        cursor = source_connection.execute(
            """
            WITH ranked AS (
                SELECT page_id,
                       ROW_NUMBER() OVER (ORDER BY page_id) AS row_number,
                       COUNT(*) OVER () AS total_rows
                FROM pages
                WHERE dump_id = ?
            )
            SELECT p.page_id, p.title, p.namespace_id, p.namespace_name,
                   p.revision_id, p.text_length, p.page_text
            FROM ranked AS r
            JOIN pages AS p
              ON p.dump_id = ? AND p.page_id = r.page_id
            WHERE ((r.row_number - 1) * ? / r.total_rows)
                  != (r.row_number * ? / r.total_rows)
            ORDER BY p.page_id
            """,
            (source_dump_id, source_dump_id, sample_size, sample_size),
        )
        inserted = 0
        while True:
            rows = cursor.fetchmany(250)
            if not rows:
                break
            scratch_connection.executemany(
                """
                INSERT INTO pages
                (dump_id, page_id, title, namespace_id, namespace_name,
                 revision_id, text_length, page_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (1, row["page_id"], row["title"], row["namespace_id"],
                     row["namespace_name"], row["revision_id"],
                     row["text_length"], row["page_text"])
                    for row in rows
                ],
            )
            inserted += len(rows)
        scratch_connection.commit()
        return inserted
    finally:
        source_connection.close()


def run_sample(source_database_path, source_dump_id, source_name, sample_size, batch_size):
    original_database_path = database.DATABASE_PATH
    with tempfile.TemporaryDirectory(prefix=f"tamriel_benchmark_{sample_size}_") as folder:
        scratch_path = Path(folder) / "benchmark.sqlite3"
        export_path = Path(folder) / "knowledge_base.json"
        database.DATABASE_PATH = scratch_path
        try:
            database.initialise_database()
            scratch_connection = database.get_connection()
            try:
                scratch_connection.execute(
                    "INSERT INTO source_dumps (dump_id, source_name, import_status) "
                    "VALUES (1, ?, 'completed')",
                    (f"benchmark:{source_name}:{sample_size}",),
                )
                copied = copy_evenly_spaced_pages(
                    source_database_path, source_dump_id, sample_size, scratch_connection
                )
            finally:
                scratch_connection.close()

            started = perf_counter()
            analysis = analyse_dump(1, batch_size=batch_size)
            analysis_elapsed = perf_counter() - started

            started = perf_counter()
            export = build_knowledge_base(1, output_path=export_path)
            export_elapsed = perf_counter() - started

            print(f"\n===== SAMPLE: {copied:,} PAGES =====")
            print(f"Analysis total: {analysis_elapsed:.2f} seconds")
            for stage, elapsed in analysis["stage_timings"].items():
                print(f"  {stage.replace('_', ' ').title()}: {elapsed:.2f} seconds")
            print(f"Knowledge-base export: {export_elapsed:.2f} seconds")
            print(f"Wiki links: {analysis['wiki_links_extracted']:,}")
            print(f"Template parameters: {analysis['template_parameters_extracted']:,}")
            print(f"Candidate fact matches: {analysis['candidate_facts_extracted']:,}")
            print(f"Exported knowledge facts: {export['knowledge_facts']:,}")
            print(f"Page throughput: {copied / analysis_elapsed:,.1f} pages/second"
                  if analysis_elapsed else "Page throughput: unavailable")
        finally:
            database.DATABASE_PATH = original_database_path


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Bottom-Up analysis without modifying the main database."
    )
    parser.add_argument(
        "--sizes", nargs="+", type=int, default=[100, 1000, 10000, 50000],
        help="Sample sizes to test (default: 100 1000 10000 50000).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=250,
        help="Analysis batch size (default: 250).",
    )
    args = parser.parse_args()
    if args.batch_size < 1 or any(size < 1 for size in args.sizes):
        parser.error("Sample sizes and batch size must be at least 1.")

    source_database_path = database.DATABASE_PATH
    source_dump_id, source_name, available_pages = get_source_dump()
    print(f"Source dump: {source_name} (ID {source_dump_id})")
    print(f"Available pages: {available_pages:,}")
    print("Samples are evenly spaced across page IDs.")
    print("Each sample runs in a temporary SQLite database.")
    print("The main database and knowledge_base.json are not modified.")

    for size in args.sizes:
        if size > available_pages:
            print(f"\nSkipping {size:,}: only {available_pages:,} pages are available.")
            continue
        run_sample(source_database_path, source_dump_id, source_name, size, args.batch_size)


if __name__ == "__main__":
    main()
