"""Tests for the isolated expanded-knowledge extraction experiment."""
import unittest

from experiments.expanded_knowledge_candidates.extractor import (
    extract_uesp_observations,
    group_observations_by_source,
    make_external_observation,
)


class ExpandedKnowledgeCandidateTests(unittest.TestCase):
    def test_extracts_race_and_occupation_fields(self):
        page = {
            "page_id": "101",
            "title": "Example Character",
            "text": (
                "{{Character Summary\n"
                "|race=Nord\n"
                "|occupation=Scholar\n"
                "}}"
            ),
        }
        results = extract_uesp_observations(page, "uesp-2026-11-01.xml.bz2")
        values = {(item["entity_type"], item["value"]) for item in results}
        self.assertIn(("race", "Nord"), values)
        self.assertIn(("occupation", "Scholar"), values)
        self.assertTrue(all(
            item["provenance"]["source_type"] == "uesp" for item in results
        ))

    def test_book_field_and_book_template_are_candidates(self):
        page = {
            "page_id": "202",
            "title": "The Example Book",
            "text": (
                "{{Book Summary\n"
                "|author=Example Author\n"
                "|book=The Example Book\n"
                "}}"
            ),
        }
        results = extract_uesp_observations(page, "uesp-2026-11-01.xml.bz2")
        self.assertTrue(any(item["entity_type"] == "book" for item in results))
        self.assertTrue(any(
            item["entity_type"] == "book"
            and item["value"] == "The Example Book"
            for item in results
        ))

    def test_generic_title_field_is_not_assumed_to_be_a_book(self):
        page = {
            "page_id": "303",
            "title": "Example Place",
            "text": "{{Place Summary|title=Example Place|race=}}",
        }
        results = extract_uesp_observations(page, "dump.xml.bz2")
        self.assertFalse(any(item["entity_type"] == "book" for item in results))

    def test_user_and_mod_observations_keep_separate_provenance(self):
        user_fact = make_external_observation(
            "race", "Example Character", "Breton",
            "User-provided character change.", "user", "submission-001",
        )
        mod_fact = make_external_observation(
            "race", "Example Character", "Altmer",
            "Race override in the example mod.", "mod", "mod-package-77",
            mod_id="example-race-overhaul",
        )
        grouped = group_observations_by_source([user_fact, mod_fact])
        self.assertEqual(len(grouped), 2)
        self.assertEqual(user_fact["provenance"]["source_type"], "user")
        self.assertEqual(mod_fact["provenance"]["source_type"], "mod")
        self.assertEqual(
            mod_fact["provenance"]["mod_id"], "example-race-overhaul"
        )

    def test_mod_observation_requires_mod_id(self):
        with self.assertRaises(ValueError):
            make_external_observation(
                "occupation", "Example Character", "Mage", "Evidence",
                "mod", "package-1",
            )

    def test_external_observation_rejects_unknown_source_type(self):
        with self.assertRaises(ValueError):
            make_external_observation(
                "race", "Example Character", "Nord", "Evidence",
                "uesp", "dump-1",
            )


if __name__ == "__main__":
    unittest.main()
