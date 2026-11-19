"""End-to-end tests for the committed five-page UESP sample workflow."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bottom_up import run_sample_analysis, run_sample_import


class SampleWorkflowTests(unittest.TestCase):
    def test_sample_import_analysis_and_link_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            sample_db = Path(directory) / "sample.db"

            with patch.object(run_sample_import, "SAMPLE_DATABASE_PATH", sample_db):
                run_sample_import.import_sample()

            with patch.object(run_sample_analysis, "SAMPLE_DATABASE_PATH", sample_db):
                pages = run_sample_analysis.load_sample_pages()

            self.assertEqual(len(pages), 5)
            self.assertTrue(any(page["title"] == "Skyrim" for page in pages))

            results = run_sample_analysis.analyse_sample_pages(pages)
            self.assertEqual(len(results), 5)
            self.assertTrue(all("analysis" in result for result in results))

            links = run_sample_analysis.extract_link_records(results)
            self.assertTrue(links)
            self.assertTrue(
                all({"source_page", "destination", "destination_title", "display_text"} <= link.keys()
                    for link in links)
            )

    def test_analysis_runner_reports_missing_sample_database(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_db = Path(directory) / "missing.db"
            with patch.object(run_sample_analysis, "SAMPLE_DATABASE_PATH", missing_db):
                with self.assertRaisesRegex(FileNotFoundError, "run"):
                    run_sample_analysis.load_sample_pages()


if __name__ == "__main__":
    unittest.main()
