"""Tests for the first bottom-up machine-learning prototype."""

import bz2
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ai.bottom_up.clustering import discover_page_clusters
from src.database import database
from src.ingestion.namespaces import read_namespaces
from src.ingestion.xml_reader import inter_page_data


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_wiki_dump.xml.fixture"


class BottomUpClusteringTests(unittest.TestCase):
    def test_discovers_groups_from_synthetic_wiki_pages(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            temp_path = Path(temp_directory)
            dump_path = temp_path / "sample_wiki_dump.xml.bz2"
            database_path = temp_path / "test_database.db"

            with FIXTURE_PATH.open("rb") as source_file:
                with bz2.open(dump_path, "wb") as dump_file:
                    dump_file.write(source_file.read())

            with patch.object(database, "DATABASE_PATH", database_path):
                database.initialise_database()
                database.migrate_database()

                dump_id = database.register_source_dump(dump_path.name)
                database.insert_pages_batch(
                    dump_id,
                    inter_page_data(dump_path),
                    read_namespaces(dump_path),
                    batch_size=4,
                )

                pages = database.get_pages_for_analysis(namespace_id=0)
                results = discover_page_clusters(
                    pages,
                    number_of_clusters=2,
                )

                self.assertEqual(results["algorithm"], "TF-IDF + K-means")
                self.assertEqual(results["page_count"], 5)
                self.assertEqual(results["cluster_count"], 2)

                clustered_titles = [
                    page["title"]
                    for cluster in results["clusters"]
                    for page in cluster["pages"]
                ]
                self.assertEqual(
                    set(clustered_titles),
                    {
                        "Skyrim",
                        "Oblivion",
                        "Morrowind",
                        "Daggerfall",
                        "Revision history example",
                    },
                )

                self.assertTrue(
                    all(
                        cluster["representative_terms"]
                        for cluster in results["clusters"]
                        if cluster["page_count"] > 0
                    )
                )

    def test_rejects_more_clusters_than_available_pages(self):
        pages = [
            {"page_id": 1, "title": "One", "page_text": "A page about dragons."},
            {"page_id": 2, "title": "Two", "page_text": "A page about castles."},
        ]

        with self.assertRaises(ValueError):
            discover_page_clusters(pages, number_of_clusters=3)


if __name__ == "__main__":
    unittest.main()
