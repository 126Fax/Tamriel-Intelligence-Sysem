#!/usr/bin/env python3
"""Compare Python and Rust extraction on selected real pages, read-only."""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import mwparserfromhell

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from bottom_up.full_pipeline import (
    _compile_province_patterns,
    extract_candidate_facts,
    extract_template_parameters,
)
from bottom_up.province_catalog import load_provinces
from experiments.expanded_knowledge_candidates.extractor import (
    extract_uesp_observations,
)
from src.analysis.content_structure import analyse_wiki_markup


DEFAULT_DATABASE = PROJECT_ROOT / "data/database/tamriel_intelligence_rust.db"
DEFAULT_PAGE_IDS = (159542, 302203, 2388, 507839)


def normalize_template_name(value):
    return " ".join(value.replace("_", " ").split()).casefold()


def canonical_parameter_value(value):
    lines = [
        line.lstrip().lstrip("*#;:").strip()
        for line in value.splitlines()
    ]
    return " ".join(" ".join(lines).split())


def reference_parameter_value(parameter):
    raw_value = parameter["raw_value"]
    if re.search(r"<br\s*/?>", raw_value, re.IGNORECASE):
        source = re.sub(r"<br\s*/?>", " ", raw_value, flags=re.IGNORECASE)
        value = mwparserfromhell.parse(source).strip_code(
            normalize=True, collapse=True
        ).strip()
    else:
        value = parameter["parameter_value"]
    return canonical_parameter_value(value)


def build_expected_page(page, source_name, provinces, province_patterns):
    text = page["text"] or ""
    wikicode = mwparserfromhell.parse(text)
    structure = analyse_wiki_markup(text)
    links = [
        {
            "destination": str(link.title).strip(),
            "display_text": (
                str(link.text).strip() if link.text is not None
                else str(link.title).strip()
            ),
        }
        for link in wikicode.filter_wikilinks()
    ]
    plain_text = wikicode.strip_code(normalize=True, collapse=True)
    templates = [
        normalize_template_name(str(template.name))
        for template in wikicode.filter_templates()
    ]
    parameters = extract_template_parameters(
        wikicode, page["page_id"], page["title"]
    )
    observations = extract_uesp_observations(page, source_name)
    title_fragment = page["title"].rsplit(":", 1)[-1].strip()

    return {
        "template_counts": dict(Counter(templates)),
        "template_parameters": [
            {
                "template": normalize_template_name(item["template_name"]),
                "name": item["parameter_name"],
                "named": item["is_named"],
                "value": reference_parameter_value(item),
            }
            for item in parameters
        ],
        "links": links,
        "headings": [
            heading.title.strip_code().strip()
            for heading in wikicode.filter_headings()
        ],
        "reference_count": structure["tag_names"].get("ref", 0),
        "categories": sorted(
            destination.split(":", 1)[1]
            for destination, _ in (
                (item["destination"], item["display_text"]) for item in links
            )
            if destination.casefold().startswith("category:")
        ),
        "external_urls": [
            str(link.url).strip() for link in wikicode.filter_external_links()
        ],
        "text_contains": (
            [title_fragment]
            if title_fragment.casefold() in plain_text.casefold()
            else []
        ),
        "facts": extract_candidate_facts(
            plain_text,
            page["page_id"],
            page["title"],
            provinces,
            province_patterns,
        ),
        "typed_candidates": [
            {"entity_type": item["entity_type"], "value": item["value"]}
            for item in observations
        ],
    }


def load_real_pages(database_path, dump_id, page_ids, provinces, province_patterns):
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        dump = connection.execute(
            "SELECT source_name FROM source_dumps WHERE dump_id = ? "
            "AND import_status = 'completed'",
            (dump_id,),
        ).fetchone()
        if dump is None:
            raise ValueError(f"dump {dump_id} is missing or not completed")
        placeholders = ",".join("?" for _ in page_ids)
        rows = connection.execute(
            f"""
            SELECT page_id,title,namespace_id,revision_id,page_text
            FROM pages
            WHERE dump_id = ? AND page_id IN ({placeholders})
            ORDER BY page_id
            """,
            (dump_id, *page_ids),
        ).fetchall()
        found_ids = {row["page_id"] for row in rows}
        missing_ids = sorted(set(page_ids) - found_ids)
        if missing_ids:
            raise ValueError(f"page IDs not present in dump {dump_id}: {missing_ids}")
        source_name = dump["source_name"]
        pages = []
        for row in rows:
            page = dict(row)
            page["namespace"] = page.pop("namespace_id")
            page["revision_id"] = page["revision_id"] or 0
            page["text"] = page.pop("page_text")
            page["expected"] = build_expected_page(
                page, source_name, provinces, province_patterns
            )
            pages.append(page)
        return source_name, pages
    finally:
        connection.close()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--dump-id", type=int)
    parser.add_argument(
        "--page-id",
        type=int,
        action="append",
        dest="page_ids",
        help="Page ID to compare; repeat to select multiple pages.",
    )
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"database does not exist: {args.database}")

    connection = sqlite3.connect(
        f"{args.database.resolve().as_uri()}?mode=ro", uri=True
    )
    try:
        dump = connection.execute(
            """
            SELECT dump_id FROM source_dumps
            WHERE import_status = 'completed'
            ORDER BY dump_id DESC LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    if args.dump_id is None:
        if dump is None:
            parser.error("database has no completed dump")
        args.dump_id = dump[0]
    page_ids = args.page_ids or list(DEFAULT_PAGE_IDS)
    if not page_ids:
        parser.error("at least one --page-id is required")

    provinces = load_provinces()
    province_patterns = _compile_province_patterns(provinces)
    source_name, pages = load_real_pages(
        args.database, args.dump_id, page_ids, provinces, province_patterns
    )
    fixture = {"source_name": source_name, "pages": pages}

    with tempfile.TemporaryDirectory(prefix="tis-real-parity-") as directory:
        fixture_path = Path(directory) / "real_pages.json"
        fixture_path.write_text(
            json.dumps(fixture, ensure_ascii=False), encoding="utf-8"
        )
        environment = os.environ.copy()
        environment["TIS_EXTRACTION_PARITY_FIXTURE"] = str(fixture_path)

        commands = (
            (
                "Python reference parity",
                [
                    str(Path(sys.prefix) / "bin" / "python"),
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(PROJECT_ROOT / "tests"),
                    "-p",
                    "test_extraction_parity.py",
                    "-v",
                ],
            ),
            (
                "Rust parity",
                [
                    "cargo",
                    "test",
                    "--manifest-path",
                    str(PROJECT_ROOT / "rust-version/Cargo.toml"),
                    "--test",
                    "extraction_parity_tests",
                    "--",
                    "--nocapture",
                ],
            ),
        )
        for label, command in commands:
            print(f"\n== {label} ==")
            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                check=True,
            )

    print(
        f"\nParity checks passed for {len(pages)} real pages "
        f"from dump {args.dump_id}. Temporary page text was removed."
    )


if __name__ == "__main__":
    run()
