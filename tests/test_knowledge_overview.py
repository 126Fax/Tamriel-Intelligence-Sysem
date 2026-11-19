import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from top_down.knowledge_overview import (
    build_knowledge_overview,
    format_knowledge_overview,
    is_knowledge_overview_question,
    load_explicit_facts,
)
from top_down.question_analyser import analyse_question, answer_question


class KnowledgeOverviewTests(unittest.TestCase):
    def test_recognises_common_overview_questions(self):
        for question in (
            "What do you know?",
            "tell me everything you know",
            "Show me what you know",
            "What do you know about Skyrim?",
        ):
            with self.subTest(question=question):
                self.assertTrue(is_knowledge_overview_question(question))

    def test_does_not_misclassify_ordinary_questions(self):
        self.assertFalse(is_knowledge_overview_question("Where do dragons live?"))

    def test_analyser_assigns_knowledge_overview_intent(self):
        result = analyse_question("What do you know?")
        self.assertEqual(result["intent"], "knowledge_overview")

    def test_loads_structured_facts(self):
        facts = [{"subject": "Skyrim", "relationship": "province", "object": "Empire"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facts.json"
            path.write_text(json.dumps(facts), encoding="utf-8")
            self.assertEqual(load_explicit_facts(path), facts)

    def test_overview_lists_facts_and_explains_source_material(self):
        facts = [{"subject": "Skyrim", "relationship": "province", "object": "Empire"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facts.json"
            path.write_text(json.dumps(facts), encoding="utf-8")
            with patch(
                "top_down.knowledge_overview.get_database_overview",
                return_value={
                    "available": True,
                    "page_count": 12,
                    "namespaces": [{"namespace_name": "Main", "page_count": 12}],
                    "dumps": [],
                },
            ):
                overview = build_knowledge_overview(path)

        answer = format_knowledge_overview(overview)
        self.assertIn("1 structured fact", answer)
        self.assertIn("Skyrim — province — Empire", answer)
        self.assertIn("12 imported wiki page(s)", answer)
        self.assertIn("not automatically understood", answer)

    def test_answer_question_handles_overview_request(self):
        with patch(
            "top_down.knowledge_overview.answer_knowledge_overview",
            return_value="overview",
        ) as answer:
            self.assertEqual(answer_question("What do you know?"), "overview")
            answer.assert_called_once_with("What do you know?")


if __name__ == "__main__":
    unittest.main()
