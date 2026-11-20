"""Measure repository-wide workloads without changing production code.

Safe default: inspect the database, run the unit tests, and time representative
Top-Down queries. Rebuilding Bottom-Up analysis is opt-in because it clears and
recreates derived analysis tables and rewrites knowledge_base.json.

Run from the repository root:
    python -m experiments.full_repository_performance.profile_repository
    python -m experiments.full_repository_performance.profile_repository --run-bottom-up
    python -m experiments.full_repository_performance.profile_repository --run-bottom-up --include-import
"""
from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from src.database import database

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "data" / "performance"


def database_snapshot() -> dict:
    """Collect read-only row counts for the main project database."""
    connection = database.get_connection()
    try:
        tables = {
            row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        snapshot = {"database_path": str(database.DATABASE_PATH), "tables": {}}
        for table in (
            "source_dumps", "pages", "page_analysis",
            "page_template_parameters", "page_links", "candidate_facts",
        ):
            if table in tables:
                snapshot["tables"][table] = connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
        dumps = []
        if "source_dumps" in tables:
            dumps = [
                dict(row) for row in connection.execute(
                    "SELECT dump_id, source_name, import_status FROM source_dumps "
                    "ORDER BY dump_id"
                )
            ]
        snapshot["source_dumps"] = dumps
        return snapshot
    finally:
        connection.close()


def run_unit_tests() -> dict:
    """Run the existing unittest suite and capture its output and duration."""
    started = perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests",
         "-p", "test_*.py", "-v"],
        cwd=PROJECT_ROOT, text=True, capture_output=True, check=False,
    )
    return {
        "elapsed_seconds": perf_counter() - started,
        "return_code": result.returncode,
        "passed": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_top_down_workload() -> list[dict]:
    """Time question interpretation, retrieval and answer generation together."""
    from top_down.assistant import answer_question

    questions = (
        "What do you know about Skyrim?",
        "How many provinces are there?",
        "Where is Vivec?",
        "Tell me about the Empire.",
    )
    results = []
    for question in questions:
        started = perf_counter()
        try:
            answer = answer_question(question)
            results.append({
                "question": question,
                "elapsed_seconds": perf_counter() - started,
                "intent": answer["analysis"]["intent"],
                "facts_returned": len(answer["facts"]),
                "answer_characters": len(answer["answer"]),
                "error": None,
            })
        except Exception as error:  # report one failed query without hiding others
            results.append({
                "question": question,
                "elapsed_seconds": perf_counter() - started,
                "error": f"{type(error).__name__}: {error}",
            })
    return results


def run_bottom_up(args, dump_id: int | None) -> dict:
    """Optionally profile analysis and knowledge-base export.

    WARNING: analyse_dump clears and rebuilds derived rows for the selected dump.
    build_knowledge_base replaces the project's knowledge_base.json.
    """
    from bottom_up.full_pipeline import DEFAULT_BATCH_SIZE, analyse_dump, build_knowledge_base
    from config.paths import get_xml_dump_path
    from src.ingestion.importer import import_dump

    result = {"import": None, "analysis": None, "export": None}
    if args.include_import:
        dump_path = get_xml_dump_path()
        profiler = cProfile.Profile()
        started = perf_counter()
        import_result = profiler.runcall(import_dump, dump_path, args.import_batch_size)
        elapsed = perf_counter() - started
        result["import"] = {**import_result, "profiled_elapsed_seconds": elapsed}
        result["import_profile"] = profiler

        connection = database.get_connection()
        try:
            row = connection.execute(
                "SELECT dump_id FROM source_dumps WHERE source_name = ? "
                "ORDER BY dump_id DESC LIMIT 1", (dump_path.name,)
            ).fetchone()
            dump_id = row["dump_id"] if row else None
        finally:
            connection.close()

    if dump_id is None:
        raise RuntimeError(
            "No imported dump was found. Import the dump first, or use --include-import."
        )

    profiler = cProfile.Profile()
    started = perf_counter()
    analysis = profiler.runcall(
        analyse_dump, dump_id, args.analysis_batch_size
    )
    analysis_elapsed = perf_counter() - started
    result["analysis"] = {
        **analysis,
        "profiled_elapsed_seconds": analysis_elapsed,
        "pages_per_second": (
            analysis["pages_analysed"] / analysis_elapsed if analysis_elapsed else 0
        ),
    }
    result["analysis_profile"] = profiler

    export_started = perf_counter()
    export = build_knowledge_base(dump_id)
    result["export"] = {
        **export, "elapsed_seconds": perf_counter() - export_started
    }
    return result


def save_profile(profiler: cProfile.Profile, path: Path, label: str) -> str:
    profiler.dump_stats(str(path))
    lines = []
    stats = pstats.Stats(profiler).strip_dirs().sort_stats("cumulative")
    stats.stream = _ListStream(lines)
    stats.print_stats(40)
    text_path = path.with_suffix(".txt")
    text_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{label} profile: {path}")
    print(f"{label} top-functions report: {text_path}")
    return str(path)


class _ListStream:
    def __init__(self, lines):
        self.lines = lines

    def write(self, value):
        self.lines.append(value.rstrip("\n"))

    def flush(self):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Time the main Tamriel Intelligence System workloads."
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Do not run the automated unit-test suite.",
    )
    parser.add_argument(
        "--run-bottom-up", action="store_true",
        help="Rebuild Bottom-Up analysis and knowledge_base.json (changes derived data).",
    )
    parser.add_argument(
        "--include-import", action="store_true",
        help="Also stream/import the configured XML dump before analysis.",
    )
    parser.add_argument("--dump-id", type=int, help="Existing source_dumps ID to analyse.")
    parser.add_argument("--import-batch-size", type=int, default=2500)
    parser.add_argument("--analysis-batch-size", type=int, default=32000)
    args = parser.parse_args()

    if args.include_import and not args.run_bottom_up:
        parser.error("--include-import requires --run-bottom-up.")
    if args.import_batch_size < 1 or args.analysis_batch_size < 1:
        parser.error("Batch sizes must be at least 1.")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "database_before": database_snapshot(),
    }

    print("=== Tamriel Intelligence System: repository performance report ===")
    print(f"Database: {report['database_before']['database_path']}")
    print("Database snapshot:")
    for table, count in report["database_before"]["tables"].items():
        print(f"  {table}: {count:,}")

    if not args.skip_tests:
        print("\nRunning automated tests...")
        report["unit_tests"] = run_unit_tests()
        print(f"Tests: {report['unit_tests']['elapsed_seconds']:.2f}s "
              f"(passed={report['unit_tests']['passed']})")
        if not report["unit_tests"]["passed"]:
            print(report["unit_tests"]["stderr"][-4000:])

    print("\nTiming representative Top-Down questions...")
    report["top_down"] = run_top_down_workload()
    for item in report["top_down"]:
        print(f"  {item['elapsed_seconds']:.4f}s | {item['question']} "
              f"| facts={item.get('facts_returned', 0)}")

    if args.run_bottom_up:
        dump_id = args.dump_id
        if dump_id is None and not args.include_import:
            dumps = report["database_before"]["source_dumps"]
            if dumps:
                dump_id = dumps[-1]["dump_id"]
        print("\nRunning profiled Bottom-Up pipeline...")
        print("WARNING: this rebuilds derived analysis rows and replaces knowledge_base.json.")
        bottom_up = run_bottom_up(args, dump_id)
        for key in ("import_profile", "analysis_profile"):
            profiler = bottom_up.pop(key, None)
            if profiler is not None:
                save_profile(profiler, REPORT_DIR / f"{key}_{stamp}.prof", key)
        report["bottom_up"] = bottom_up
        analysis = bottom_up["analysis"]
        print(f"Analysis: {analysis['profiled_elapsed_seconds']:.2f}s "
              f"| {analysis['pages_analysed']:,} pages "
              f"| {analysis['pages_per_second']:,.1f} pages/s")
        for stage, seconds in analysis["stage_timings"].items():
            print(f"  {stage}: {seconds:.2f}s")
        print(f"Knowledge-base export: {bottom_up['export']['elapsed_seconds']:.2f}s")

    report["database_after"] = database_snapshot()
    report_path = REPORT_DIR / f"repository_performance_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"\nReport saved to: {report_path}")
    return 0 if report.get("unit_tests", {}).get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
