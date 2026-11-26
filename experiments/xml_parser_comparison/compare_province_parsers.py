"""Compare the repository's lxml reader with the experimental xmlstream reader.

Both readers process the same compressed MediaWiki dump and feed page text into
the same Bottom-Up fact extractor. Each reader runs in a separate subprocess so
peak RSS measurements are independent. No database or knowledge-base files are
written.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

import mwparserfromhell

from bottom_up.full_pipeline import extract_candidate_facts
from bottom_up.province_catalog import audit_discovered_provinces, load_provinces

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DUMP = PROJECT_ROOT / "data" / "raw" / "uespwiki-2026-11-01-current.xml.bz2"
MEDIAWIKI_NS = "http://www.mediawiki.org/xml/export-0.10/"
NS = f"{{{MEDIAWIKI_NS}}}"


def page_data_from_xmlstream_content(content: str) -> dict[str, str] | None:
    """Decode one xmlstream page callback with Python's standard XML parser."""
    wrapped = f'<page xmlns="{MEDIAWIKI_NS}">{content}</page>'
    page = ET.fromstring(wrapped)
    revisions = page.findall(f"{NS}revision")
    if not revisions:
        return None

    latest_revision = revisions[-1]
    revision_text = latest_revision.findtext(f"{NS}text")
    if revision_text is None:
        return None

    return {
        "page_id": page.findtext(f"{NS}id"),
        "title": page.findtext(f"{NS}title"),
        "namespace": page.findtext(f"{NS}ns"),
        "revision_id": latest_revision.findtext(f"{NS}id"),
        "text": revision_text,
    }


def process_page(page_data: dict, facts: list[dict], digest, provinces: list[str]) -> None:
    """Apply the same wiki parsing and fact extraction to either reader."""
    encoded = json.dumps(
        page_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)

    wikicode = mwparserfromhell.parse(page_data.get("text") or "")
    plain_text = wikicode.strip_code(normalize=True, collapse=True)
    facts.extend(
        extract_candidate_facts(
            plain_text,
            page_data["page_id"],
            page_data["title"],
            provinces=provinces,
        )
    )


def run_lxml(dump_path: Path) -> dict:
    from src.ingestion.xml_reader import extract_page_data, read_pages

    facts: list[dict] = []
    digest = hashlib.sha256()
    provinces = load_provinces()
    pages_processed = pages_seen = 0
    started = time.perf_counter()

    for page in read_pages(dump_path):
        pages_seen += 1
        page_data = extract_page_data(page)
        if page_data is None:
            continue
        process_page(page_data, facts, digest, provinces)
        pages_processed += 1

    elapsed = time.perf_counter() - started
    return make_report(
        "lxml", pages_processed, facts, digest.hexdigest(), elapsed,
        pages_seen - pages_processed,
    )


def run_xmlstream(dump_path: Path, chunk_size: int, max_buffer_size: int) -> dict:
    from xmlstream import StreamingXMLParser, TagBehavior, TagConfig

    facts: list[dict] = []
    digest = hashlib.sha256()
    provinces = load_provinces()
    pages_seen = pages_processed = 0

    def on_page_complete(tag_name: str, content: str) -> None:
        nonlocal pages_seen, pages_processed
        pages_seen += 1
        page_data = page_data_from_xmlstream_content(content)
        if page_data is None:
            return
        process_page(page_data, facts, digest, provinces)
        pages_processed += 1

    config = TagConfig(
        name="page",
        behavior=TagBehavior.SILENT,
        complete_callback=on_page_complete,
    )
    parser = StreamingXMLParser({"page": config}, max_buffer_size=max_buffer_size)

    started = time.perf_counter()
    with bz2.open(dump_path, "rt", encoding="utf-8") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            for _event in parser.process_chunk(chunk):
                pass

    elapsed = time.perf_counter() - started
    return make_report(
        "xmlstream", pages_processed, facts, digest.hexdigest(), elapsed,
        pages_seen - pages_processed,
    )


def make_report(
    parser_name: str, pages_processed: int, facts: list[dict], digest: str,
    elapsed: float, pages_without_text: int,
) -> dict:
    audit = audit_discovered_provinces(facts)
    evidence_counts = {
        name: len(records) for name, records in audit["discovered"].items()
    }

    try:
        import resource
        peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except (ImportError, AttributeError):
        peak_rss_mb = None

    return {
        "parser": parser_name,
        "pages_processed": pages_processed,
        "pages_without_text": pages_without_text,
        "record_sha256": digest,
        "expected_provinces": audit["expected_count"],
        "discovered_provinces": audit["discovered_count"],
        "province_evidence_records": sum(evidence_counts.values()),
        "province_evidence_by_name": evidence_counts,
        "missing_provinces": audit["missing"],
        "unexpected_candidates": [
            {
                "subject": fact.get("subject"),
                "relationship": fact.get("relationship"),
                "object": fact.get("object"),
                "source_page": fact.get("source_page"),
            }
            for fact in audit["unexpected_candidates"]
        ],
        "elapsed_seconds": round(elapsed, 3),
        "pages_per_second": round(pages_processed / elapsed, 2) if elapsed else 0,
        "peak_rss_mb": round(peak_rss_mb, 2) if peak_rss_mb is not None else None,
    }


def worker(args) -> int:
    dump_path = Path(args.dump).expanduser().resolve()
    if not dump_path.is_file():
        raise FileNotFoundError(f"XML dump not found: {dump_path}")

    if args.worker == "lxml":
        report = run_lxml(dump_path)
    else:
        report = run_xmlstream(
            dump_path, chunk_size=args.chunk_size,
            max_buffer_size=args.max_buffer_size,
        )

    print(json.dumps(report, ensure_ascii=False))
    return 0


def run_isolated_worker(args, parser_name: str) -> dict:
    command = [
        sys.executable,
        "-m",
        "experiments.xml_parser_comparison.compare_province_parsers",
        "--worker",
        parser_name,
        "--dump",
        str(Path(args.dump).expanduser().resolve()),
        "--chunk-size",
        str(args.chunk_size),
        "--max-buffer-size",
        str(args.max_buffer_size),
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{parser_name} worker failed (exit {completed.returncode}).\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def print_comparison(lxml_report: dict, xmlstream_report: dict) -> None:
    print("\n===== XML PARSER COMPARISON =====")
    for report in (lxml_report, xmlstream_report):
        print(f"\n{report['parser'].upper()}")
        print(f"Pages processed: {report['pages_processed']:,}")
        print(f"Pages without usable revision text: {report['pages_without_text']:,}")
        print(
            f"Provinces identified: {report['discovered_provinces']}/"
            f"{report['expected_provinces']}"
        )
        print(f"Province evidence records: {report['province_evidence_records']}")
        for name, count in report["province_evidence_by_name"].items():
            print(f"  - {name}: {count}")
        print(f"Missing provinces: {report['missing_provinces']}")
        print(f"Elapsed: {report['elapsed_seconds']:.3f} seconds")
        print(f"Throughput: {report['pages_per_second']:,.2f} pages/second")
        print(f"Peak RSS: {report['peak_rss_mb']} MB")
        print(f"Page-record SHA-256: {report['record_sha256']}")

    same_count = lxml_report["pages_processed"] == xmlstream_report["pages_processed"]
    same_empty = lxml_report["pages_without_text"] == xmlstream_report["pages_without_text"]
    same_records = lxml_report["record_sha256"] == xmlstream_report["record_sha256"]
    same_provinces = (
        lxml_report["province_evidence_by_name"]
        == xmlstream_report["province_evidence_by_name"]
    )
    same_unexpected = (
        lxml_report["unexpected_candidates"]
        == xmlstream_report["unexpected_candidates"]
    )

    print("\n===== MATCH CHECKS =====")
    print(f"Same processed page count: {same_count}")
    print(f"Same pages without usable text: {same_empty}")
    print(f"Identical extracted page records: {same_records}")
    print(f"Same province evidence counts: {same_provinces}")
    print(f"Same unexpected candidates: {same_unexpected}")

    if all((same_count, same_empty, same_records, same_provinces, same_unexpected)):
        print("\nRESULT: Both parsers produced matching page records and province results.")
    else:
        print("\nRESULT: The parsers do not yet produce equivalent results.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare lxml and xmlstream on the same UESP dump."
    )
    parser.add_argument("--dump", default=str(DEFAULT_DUMP))
    parser.add_argument("--chunk-size", type=int, default=256 * 1024)
    parser.add_argument("--max-buffer-size", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--worker", choices=("lxml", "xmlstream"))
    args = parser.parse_args()

    if args.chunk_size < 1 or args.max_buffer_size < 1:
        parser.error("Chunk and maximum buffer sizes must be positive.")

    if args.worker:
        return worker(args)

    dump_path = Path(args.dump).expanduser().resolve()
    if not dump_path.is_file():
        parser.error(f"XML dump not found: {dump_path}")

    print(f"Dump: {dump_path}")
    print("Running each parser in a separate process for independent peak-memory readings.")
    print("This processes the complete dump twice and may take some time.")

    lxml_report = run_isolated_worker(args, "lxml")
    xmlstream_report = run_isolated_worker(args, "xmlstream")
    print_comparison(lxml_report, xmlstream_report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
