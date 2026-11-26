"""Shared semantic-contract tests for the Python and Rust extractors."""
import json
import os
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mwparserfromhell

from bottom_up.full_pipeline import analyse_dump, build_knowledge_base
from experiments.expanded_knowledge_candidates.extractor import (
    extract_uesp_observations,
)
from src.analysis.content_structure import analyse_wiki_markup
from src.database import database


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "extraction_parity.json"


def _normalise_template_name(value):
    return " ".join(value.replace("_", " ").split()).casefold()


def _normalise_parameter_value(value, raw_value=None):
    if raw_value and re.search(r"<br\s*/?>", raw_value, re.IGNORECASE):
        source = re.sub(r"<br\s*/?>", " ", raw_value, flags=re.IGNORECASE)
        value = mwparserfromhell.parse(source).strip_code(
            normalize=True, collapse=True
        ).strip()
    lines = [
        line.lstrip().lstrip("*#;:").strip()
        for line in value.splitlines()
    ]
    return " ".join(" ".join(lines).split())


class ExtractionParityTests(unittest.TestCase):
    def setUp(self):
        fixture_path = Path(
            os.environ.get("TIS_EXTRACTION_PARITY_FIXTURE", FIXTURE_PATH)
        )
        self.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "parity.db"
        self.database_patch = patch.object(
            database, "DATABASE_PATH", self.database_path
        )
        self.database_patch.start()
        database.initialise_database()
        database.migrate_database()
        self.dump_id = database.register_source_dump(
            self.fixture["source_name"]
        )
        pages = [
            {
                "page_id": str(page["page_id"]),
                "title": page["title"],
                "namespace": str(page["namespace"]),
                "revision_id": str(page["revision_id"]),
                "text": page["text"],
            }
            for page in self.fixture["pages"]
        ]
        database.insert_pages_batch(
            self.dump_id, pages, {0: ""}, batch_size=2
        )
        analyse_dump(self.dump_id, batch_size=2)

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_shared_contract_matches_python_pipeline_and_provenance(self):
        connection = database.get_connection()
        try:
            for page in self.fixture["pages"]:
                expected = page["expected"]
                page_id = page["page_id"]
                title = page["title"]
                wikicode = mwparserfromhell.parse(page["text"])

                with self.subTest(page=title, signal="templates"):
                    template_counts = Counter(
                        _normalise_template_name(str(template.name))
                        for template in wikicode.filter_templates()
                    )
                    self.assertEqual(
                        dict(template_counts), expected["template_counts"]
                    )

                parameter_rows = connection.execute(
                    """
                    SELECT template_name, parameter_name, is_named,
                           parameter_value, raw_value, evidence_text,
                           extraction_method,
                           source_page_id, source_title
                    FROM page_template_parameters
                    WHERE dump_id = ? AND source_page_id = ?
                    """,
                    (self.dump_id, page_id),
                ).fetchall()
                actual_parameters = {
                    (
                        _normalise_template_name(row["template_name"]),
                        row["parameter_name"],
                        bool(row["is_named"]),
                        _normalise_parameter_value(
                            row["parameter_value"], row["raw_value"]
                        ),
                    )
                    for row in parameter_rows
                }
                expected_parameters = {
                    (
                        item["template"],
                        item["name"],
                        item["named"],
                        _normalise_parameter_value(item["value"]),
                    )
                    for item in expected["template_parameters"]
                }
                with self.subTest(page=title, signal="template parameters"):
                    self.assertEqual(expected_parameters, actual_parameters)
                    for row in parameter_rows:
                        self.assertEqual(row["source_page_id"], page_id)
                        self.assertEqual(row["source_title"], title)
                        self.assertIn("{{", row["evidence_text"])
                        self.assertEqual(
                            row["extraction_method"], "template_parameter_v1"
                        )

                link_rows = connection.execute(
                    """
                    SELECT destination, display_text
                    FROM page_links
                    WHERE dump_id = ? AND source_page_id = ?
                    """,
                    (self.dump_id, page_id),
                ).fetchall()
                actual_links = Counter(
                    (row["destination"], row["display_text"])
                    for row in link_rows
                )
                expected_links = Counter(
                    (item["destination"], item["display_text"])
                    for item in expected["links"]
                )
                with self.subTest(page=title, signal="links and categories"):
                    self.assertEqual(expected_links, actual_links)
                    actual_categories = {
                        destination.split(":", 1)[1]
                        for destination, _ in actual_links
                        if destination.casefold().startswith("category:")
                    }
                    self.assertEqual(
                        set(expected["categories"]), actual_categories
                    )

                structure = analyse_wiki_markup(page["text"])
                with self.subTest(page=title, signal="sections and links"):
                    actual_headings = [
                        heading.title.strip_code().strip()
                        for heading in wikicode.filter_headings()
                    ]
                    self.assertEqual(actual_headings, expected["headings"])
                    self.assertEqual(
                        structure["external_link_count"],
                        len(expected["external_urls"]),
                    )
                    self.assertEqual(
                        structure["heading_count"], len(expected["headings"])
                    )
                    self.assertEqual(
                        structure["tag_names"].get("ref", 0),
                        expected["reference_count"],
                    )
                    plain_text = wikicode.strip_code(
                        normalize=True, collapse=True
                    )
                    for required_text in expected["text_contains"]:
                        self.assertIn(required_text, plain_text)

                fact_rows = connection.execute(
                    """
                    SELECT subject, relationship, object, evidence_text,
                           extraction_method, confidence, source_page_id,
                           source_title
                    FROM candidate_facts
                    WHERE dump_id = ? AND source_page_id = ?
                    """,
                    (self.dump_id, page_id),
                ).fetchall()
                actual_facts = {
                    (
                        row["subject"],
                        row["relationship"],
                        row["object"],
                        row["evidence_text"],
                        row["extraction_method"],
                    )
                    for row in fact_rows
                }
                expected_facts = {
                    (
                        item["subject"],
                        item["relationship"],
                        item["object"],
                        item["evidence"],
                        item["extraction_method"],
                    )
                    for item in expected["facts"]
                }
                with self.subTest(page=title, signal="facts"):
                    self.assertEqual(expected_facts, actual_facts)
                    for row in fact_rows:
                        self.assertEqual(row["source_page_id"], page_id)
                        self.assertEqual(row["source_title"], title)
                        self.assertTrue(row["evidence_text"])
                        self.assertGreaterEqual(row["confidence"], 0)
                        self.assertLessEqual(row["confidence"], 1)

                observations = extract_uesp_observations(
                    {
                        "page_id": page_id,
                        "title": title,
                        "text": page["text"],
                    },
                    self.fixture["source_name"],
                )
                actual_candidates = {
                    (item["entity_type"], item["value"])
                    for item in observations
                }
                expected_candidates = {
                    (item["entity_type"], item["value"])
                    for item in expected["typed_candidates"]
                }
                with self.subTest(page=title, signal="typed candidates"):
                    self.assertEqual(expected_candidates, actual_candidates)
                    for item in observations:
                        self.assertEqual(item["source_page_id"], page_id)
                        self.assertEqual(item["source_page"], title)
                        self.assertIn("{{", item["evidence"])
                        self.assertEqual(
                            item["provenance"]["source_type"], "uesp"
                        )
                        self.assertEqual(
                            item["provenance"]["source_id"],
                            self.fixture["source_name"],
                        )
        finally:
            connection.close()

    def test_knowledge_export_has_shared_rust_json_shape_and_evidence(self):
        output_path = Path(self.temp_dir.name) / "python-knowledge.json"
        result = build_knowledge_base(self.dump_id, output_path)
        exported = json.loads(output_path.read_text(encoding="utf-8"))
        expected_fields = {
            "subject",
            "relationship",
            "object",
            "source_page",
            "source_page_id",
            "evidence",
            "extraction_method",
            "confidence",
        }
        expected_facts = {
            (
                fact["subject"],
                fact["relationship"],
                fact["object"],
                page["title"],
                page["page_id"],
                fact["evidence"],
                fact["extraction_method"],
                fact["confidence"],
            )
            for page in self.fixture["pages"]
            for fact in page["expected"]["facts"]
        }
        actual_facts = set()
        for fact in exported:
            self.assertEqual(set(fact), expected_fields)
            self.assertIsInstance(fact["confidence"], (int, float))
            actual_facts.add(
                (
                    fact["subject"],
                    fact["relationship"],
                    fact["object"],
                    fact["source_page"],
                    fact["source_page_id"],
                    fact["evidence"],
                    fact["extraction_method"],
                    fact["confidence"],
                )
            )
        self.assertEqual(expected_facts, actual_facts)
        self.assertEqual(result["knowledge_facts"], len(expected_facts))


if __name__ == "__main__":
    unittest.main()
