"""Import the local UESP dump, analyse its pages, and build knowledge_base.json.

Run from the repository root:
    python -m bottom_up.run_full_pipeline
"""
import argparse
from time import perf_counter

from config.paths import get_xml_dump_path
from src.ingestion.importer import import_dump
from bottom_up.full_pipeline import analyse_dump, build_knowledge_base


def report_stage(name, elapsed, count=None, unit="items"):
    """Print a consistent duration and, when available, processing rate."""
    message = f"{name}: {elapsed:.2f} seconds"
    if count is not None:
        rate = count / elapsed if elapsed > 0 else 0
        message += f" | {count:,} {unit} | {rate:,.1f} {unit}/second"
    print(message)


def main():
    parser = argparse.ArgumentParser(
        description="Import and analyse the full UESP XML dump."
    )
    parser.add_argument("--batch-size", type=int, default=2500,
                        help="SQLite import and analysis batch size (default: 2500).")
    parser.add_argument("--skip-import", action="store_true",
                        help="Use pages already imported into SQLite.")
    parser.add_argument("--analysis-batch-size", type=int, default=250,
                        help="Number of pages analysed per batch (default: 250).")
    args = parser.parse_args()

    if args.batch_size < 1 or args.analysis_batch_size < 1:
        parser.error("Batch sizes must be at least 1.")

    dump_path = get_xml_dump_path()
    print(f"UESP source: {dump_path}")
    pipeline_started = perf_counter()
    import_result = None

    if args.skip_import:
        from src.database import database
        connection = database.get_connection()
        try:
            row = connection.execute(
                "SELECT dump_id FROM source_dumps WHERE source_name = ? "
                "ORDER BY dump_id DESC LIMIT 1", (dump_path.name,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            parser.error("This dump is not imported yet. Run without --skip-import.")
        dump_id = row["dump_id"]
        print(f"Using existing SQLite import (dump ID {dump_id}).")
        print("Import stage: skipped (--skip-import).")
    else:
        print("Importing XML pages into SQLite (existing pages are not duplicated)...")
        stage_started = perf_counter()
        import_result = import_dump(dump_path, batch_size=args.batch_size)
        import_elapsed = perf_counter() - stage_started
        dump_id = import_result["dump_id"]
        print(f"Pages in SQLite: {import_result['pages_in_database']:,}")
        print(f"New pages inserted: {import_result['pages_inserted']:,}")
        report_stage("Import stage", import_elapsed,
                     import_result["pages_inserted"], "new pages")

    print("Running bottom-up analysis over imported pages...")
    def report(processed, links, facts):
        print(f"  Analysed {processed:,} pages | {links:,} wiki links | "
              f"{facts:,} candidate fact matches")

    stage_started = perf_counter()
    analysis = analyse_dump(
        dump_id, batch_size=args.analysis_batch_size,
        progress_callback=report,
    )
    analysis_elapsed = perf_counter() - stage_started
    report_stage("Analysis stage", analysis_elapsed,
                 analysis["pages_analysed"], "pages")

    stage_started = perf_counter()
    knowledge = build_knowledge_base(dump_id)
    knowledge_elapsed = perf_counter() - stage_started
    report_stage("Knowledge-base export", knowledge_elapsed,
                 knowledge["knowledge_facts"], "facts")

    total_elapsed = perf_counter() - pipeline_started
    print("\n===== BOTTOM-UP RUN COMPLETE =====")
    print(f"Pages analysed: {analysis['pages_analysed']:,}")
    print(f"Wiki links extracted: {analysis['wiki_links_extracted']:,}")
    print(f"Candidate fact matches: {analysis['candidate_facts_extracted']:,}")
    print(f"Template parameters extracted: {analysis['template_parameters_extracted']:,}")
    print(f"Knowledge-base facts: {knowledge['knowledge_facts']:,}")
    print(f"Knowledge base: {knowledge['knowledge_base_path']}")
    print(f"Total elapsed: {total_elapsed:.2f} seconds")
    print("\nNote: extracted relationships are candidates backed by source-page "
          "evidence, not automatically verified lore claims.")


if __name__ == "__main__":
    main()
