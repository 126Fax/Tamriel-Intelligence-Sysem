"""Tests for the early top-down question interpretation prototype."""

import unittest

from top_down.question_analyser import (
    analyse_question,
    extract_search_term,
    identify_intent,
    identify_relationship,
    normalise_question,
)


class QuestionAnalyserTests(unittest.TestCase):
    def test_question_is_trimmed_and_casefolded(self):
        self.assertEqual(normalise_question("  WHO RULES SKYRIM?  "), "who rules skyrim?")

    def test_empty_question_is_rejected(self):
        for question in ("", "   ", None):
            with self.subTest(question=question):
                with self.assertRaises(ValueError):
                    normalise_question(question)

    def test_intents_are_recognised(self):
        self.assertEqual(identify_intent("Which provinces belong to the Empire?"), "find_subjects")
        self.assertEqual(identify_intent("Where do dragons live?"), "find_object")
        self.assertEqual(identify_intent("Explain the Dragon War"), "unknown")

    def test_search_term_removes_question_starter_and_punctuation(self):
        self.assertEqual(extract_search_term("Where do dragons live?"), "do dragons live")

    def test_relationship_detection(self):
        self.assertEqual(identify_relationship("Which provinces belong to the Empire?"), "province")
        self.assertEqual(identify_relationship("Where do dragons live?"), "lives in")
        self.assertIsNone(identify_relationship("Who rules Skyrim?"))

    def test_complete_analysis_preserves_original_question(self):
        question = "  Where do dragons live? "
        result = analyse_question(question)
        self.assertEqual(result["original_question"], question)
        self.assertEqual(result["normalised_question"], "where do dragons live?")
        self.assertEqual(result["intent"], "find_object")
        self.assertEqual(result["relationship"], "lives in")


if __name__ == "__main__":
    unittest.main()
