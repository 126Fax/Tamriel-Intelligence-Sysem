"""End-to-end tests for the first working top-down Q&A prototype."""

import json
import tempfile
import unittest
from pathlib import Path

from top_down.assistant import answer_question
from top_down.knowledge_retriever import KnowledgeBaseError, load_knowledge_base, retrieve_facts


SAMPLE_FACTS = [
    {"subject": "Skyrim", "relationship": "province", "object": "Empire"},
    {"subject": "Morrowind", "relationship": "province", "object": "Empire"},
    {"subject": "Cyrodiil", "relationship": "province", "object": "Empire"},
    {"subject": "Hammerfell", "relationship": "province", "object": "Empire"},
    {"subject": "High Rock", "relationship": "province", "object": "Empire"},
    {"subject": "Dragons", "relationship": "lives in", "object": "Skyrim"},
]


class TopDownAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "knowledge_base.json"
        self.path.write_text(json.dumps(SAMPLE_FACTS), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def ask(self, question):
        return answer_question(question, self.path)

    def test_lists_all_five_provinces(self):
        result = self.ask("Which provinces belong to the Empire?")
        self.assertEqual(len(result["facts"]), 5)
        for province in ("Skyrim", "Morrowind", "Cyrodiil", "Hammerfell", "High Rock"):
            self.assertIn(province, result["answer"])
        self.assertEqual(result["knowledge_base_records"], 6)

    def test_finds_where_dragons_live(self):
        result = self.ask("Where do dragons live?")
        self.assertEqual(result["facts"], [SAMPLE_FACTS[-1]])
        self.assertIn("Skyrim as the location for Dragons", result["answer"])

    def test_does_not_invent_who_rules_skyrim(self):
        result = self.ask("Who rules Skyrim?")
        self.assertEqual(result["facts"], [])
        self.assertIn("don't have enough information", result["answer"])

    def test_unknown_question_does_not_guess(self):
        result = self.ask("Explain the Dragon War")
        self.assertEqual(result["facts"], [])
        self.assertIn("don't have enough information", result["answer"])

    def test_case_and_spacing_do_not_prevent_retrieval(self):
        result = self.ask("  WHERE DO DRAGONS LIVE? ")
        self.assertEqual(len(result["facts"]), 1)
        self.assertIn("Skyrim", result["answer"])

    def test_load_rejects_invalid_record(self):
        self.path.write_text('[{"subject": "A"}]', encoding="utf-8")
        with self.assertRaises(KnowledgeBaseError):
            load_knowledge_base(self.path)

    def test_load_rejects_invalid_json(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(KnowledgeBaseError):
            load_knowledge_base(self.path)

    def test_retrieval_returns_no_facts_for_unknown_relationship(self):
        analysis = {
            "intent": "unknown",
            "relationship": None,
            "subject_hint": None,
            "object_hint": None,
        }
        self.assertEqual(retrieve_facts(analysis, SAMPLE_FACTS), [])


if __name__ == "__main__":
    unittest.main()
