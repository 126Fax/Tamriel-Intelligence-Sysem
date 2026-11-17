"""Tests for the Top-Down AI question-answering pipeline."""

import unittest

from top_down.answer_generator import generate_answer
from top_down.knowledge_retriever import retrieve_facts
from top_down.question_analyser import analyse_question


SAMPLE_FACTS = [
    {"subject": "Skyrim", "relationship": "province", "object": "Empire"},
    {"subject": "Morrowind", "relationship": "province", "object": "Empire"},
    {"subject": "Dragons", "relationship": "lives in", "object": "Skyrim"},
]


class QuestionAnalysisTests(unittest.TestCase):
    def test_identifies_province_relationship(self):
        result = analyse_question("Which provinces belong to the Empire?")
        self.assertEqual(result["relationship"], "province")
        self.assertEqual(result["intent"], "find_subjects")

    def test_identifies_lives_in_relationship(self):
        result = analyse_question("Where do dragons live?")
        self.assertEqual(result["relationship"], "lives in")

    def test_rejects_empty_question(self):
        with self.assertRaises(ValueError):
            analyse_question("   ")


class RetrievalTests(unittest.TestCase):
    def test_finds_provinces_of_empire(self):
        analysis = analyse_question("Which provinces belong to the Empire?")
        facts = retrieve_facts(analysis, SAMPLE_FACTS)
        self.assertEqual(
            {fact["subject"] for fact in facts},
            {"Skyrim", "Morrowind"},
        )

    def test_finds_where_dragons_live(self):
        analysis = analyse_question("Where do dragons live?")
        facts = retrieve_facts(analysis, SAMPLE_FACTS)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["object"], "Skyrim")

    def test_returns_no_facts_for_unknown_entity(self):
        analysis = analyse_question("Where do mudcrabs live?")
        self.assertEqual(retrieve_facts(analysis, SAMPLE_FACTS), [])


class AnswerGenerationTests(unittest.TestCase):
    def test_generates_province_answer(self):
        answer = generate_answer(
            "Which provinces belong to the Empire?",
            SAMPLE_FACTS[:2],
        )
        self.assertIn("Skyrim", answer)
        self.assertIn("Morrowind", answer)
        self.assertIn("Empire", answer)

    def test_handles_missing_knowledge(self):
        answer = generate_answer("Who rules Skyrim?", [])
        self.assertIn("couldn't find an answer", answer)


if __name__ == "__main__":
    unittest.main()
