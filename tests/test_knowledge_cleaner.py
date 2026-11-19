"""Tests for the explainable Knowledge Cleaner prototype."""
import json
import tempfile
import unittest
from pathlib import Path

from cleaner.knowledge_cleaner import clean_file, clean_knowledge_base, review_fact


class KnowledgeCleanerTests(unittest.TestCase):
    def candidate(self, subject="Dragons", relationship="lives in",
                  obj="Skyrim", evidence="Dragons live in Skyrim."):
        return {
            "subject": subject,
            "relationship": relationship,
            "object": obj,
            "source_page_id": 12,
            "source_page": "Dragons",
            "evidence": evidence,
            "extraction_method": "explicit_sentence_pattern_v1",
            "confidence": 0.9,
        }

    def test_approves_fact_when_evidence_supports_it(self):
        result = review_fact(self.candidate())
        self.assertEqual(result["status"], "approved")

    def test_preserves_original_provenance(self):
        fact = self.candidate()
        result = review_fact(fact)
        self.assertEqual(result["fact"], fact)
        self.assertEqual(result["fact"]["source_page_id"], 12)

    def test_rejects_subject_starting_with_conjunction(self):
        result = review_fact(self.candidate(
            subject="And I", evidence="And I live in Skyrim."
        ))
        self.assertEqual(result["status"], "rejected")

    def test_rejects_subject_containing_a_clause(self):
        result = review_fact(self.candidate(
            subject="Abishpulu Shand is a Dark Elf farmer who",
            evidence="Abishpulu Shand is a Dark Elf farmer who lives in Gnisis."
        ))
        self.assertEqual(result["status"], "rejected")

    def test_rejects_long_sentence_fragment_subject(self):
        result = review_fact(self.candidate(
            subject="2920 series suggests that Almalexia decided to",
            obj="Mournhold",
            evidence="2920 series suggests that Almalexia decided to live in Mournhold."
        ))
        self.assertEqual(result["status"], "rejected")

    def test_rejects_pronoun_object(self):
        result = review_fact(self.candidate(
            subject="After Septimus Signus dies",
            obj="it",
            evidence="After Septimus Signus dies, they live in it."
        ))
        self.assertEqual(result["status"], "rejected")

    def test_flags_evidence_that_does_not_support_fact(self):
        result = review_fact(self.candidate(
            subject="Dragons", obj="Morrowind",
            evidence="Dragons are feared throughout Skyrim."
        ))
        self.assertEqual(result["status"], "needs_review")

    def test_flags_unknown_relationship_for_review(self):
        result = review_fact(self.candidate(
            relationship="rules", evidence="The Jarl rules Skyrim."
        ))
        self.assertEqual(result["status"], "needs_review")

    def test_flags_unusually_long_possible_entity_name(self):
        result = review_fact(self.candidate(
            subject="The Imperial City Talos Plaza District",
            evidence="The Imperial City Talos Plaza District lives in Skyrim."
        ))
        self.assertEqual(result["status"], "needs_review")

    def test_rejects_missing_required_fields(self):
        result = review_fact({"subject": "Dragons"})
        self.assertEqual(result["status"], "rejected")

    def test_summary_counts_all_three_decisions(self):
        report = clean_knowledge_base([
            self.candidate(),
            self.candidate(subject="And I", evidence="And I live in Skyrim."),
            self.candidate(obj="Morrowind", evidence="Dragons are found in Skyrim."),
        ])
        self.assertEqual(report["summary"], {
            "total": 3, "approved": 1, "rejected": 1, "needs_review": 1
        })

    def test_file_runner_writes_report_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            output = Path(directory) / "review.json"
            original = [self.candidate()]
            source.write_text(json.dumps(original), encoding="utf-8")
            report = clean_file(source, output)
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), original)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()
