"""Tests for question parsing after adding structured retrieval hints."""

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
        self.assertEqual(identify_intent("Who rules Skyrim?"), "find_subjects")
        self.assertEqual(identify_intent("Explain the Dragon War"), "lookup")

    def test_search_terms_extract_the_relevant_entity(self):
        self.assertEqual(extract_search_term("Where do dragons live?"), "dragons")
        self.assertEqual(extract_search_term("Which provinces belong to the Empire?"), "empire")
        self.assertEqual(extract_search_term("Who rules Skyrim?"), "skyrim")

    def test_relationship_detection(self):
        self.assertEqual(identify_relationship("Which provinces belong to the Empire?"), "province")
        self.assertEqual(identify_relationship("Where do dragons live?"), "lives in")
        self.assertEqual(identify_relationship("Who rules Skyrim?"), "rules")
        self.assertIsNone(identify_relationship("Explain the Dragon War"))

    def test_analysis_contains_retrieval_hints(self):
        provinces = analyse_question("Which provinces belong to the Empire?")
        self.assertEqual(provinces["intent"], "find_subjects")
        self.assertEqual(provinces["object_hint"], "empire")
        self.assertIsNone(provinces["subject_hint"])

        dragons = analyse_question("Where do dragons live?")
        self.assertEqual(dragons["intent"], "find_object")
        self.assertEqual(dragons["subject_hint"], "dragons")
        self.assertEqual(dragons["relationship"], "lives in")

        ruler = analyse_question("WHO RULES SKYRIM?")
        self.assertEqual(ruler["intent"], "find_subjects")
        self.assertEqual(ruler["object_hint"], "skyrim")
        self.assertEqual(ruler["relationship"], "rules")

    def test_original_question_is_preserved(self):
        question = "  Where do dragons live? "
        result = analyse_question(question)
        self.assertEqual(result["original_question"], question)
        self.assertEqual(result["normalised_question"], "where do dragons live?")


if __name__ == "__main__":
    unittest.main()
