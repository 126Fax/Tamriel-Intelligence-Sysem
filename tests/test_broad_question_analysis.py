import unittest

from top_down.question_analyser import analyse_question, identify_intent
from top_down.database_retriever import count_entities


class BroadQuestionAnalysisTests(unittest.TestCase):
    def test_count_question_extracts_plural_target(self):
        result = analyse_question("How many farmers are there?")
        self.assertEqual(result["intent"], "count")
        self.assertEqual(result["count_target"], "farmers")

    def test_count_question_for_continents(self):
        result = analyse_question("How many continents are there?")
        self.assertEqual(result["count_target"], "continents")
        self.assertEqual(result["relationship"], "continent")

    def test_subject_lookup_extracts_named_entity(self):
        result = analyse_question("What do you know about Skyrim?")
        self.assertEqual(result["intent"], "lookup")
        self.assertEqual(result["subject_hint"], "skyrim")

    def test_who_is_question_extracts_person_or_character(self):
        result = analyse_question("Who is Vivec?")
        self.assertEqual(result["subject_hint"], "vivec")

    def test_province_count_uses_nine_name_reference_catalogue(self):
        result = count_entities("provinces")
        self.assertEqual(result["count"], 9)
        self.assertEqual(result["basis"], "curated_reference_catalog")

    def test_knowledge_overview_intent_is_recognised(self):
        self.assertEqual(identify_intent("What do you know?"), "overview")

    def test_random_fact_intent_is_recognised(self):
        self.assertEqual(identify_intent("Tell me a random fact"), "random_fact")

    def test_unknown_question_is_sent_to_search_not_crashed(self):
        self.assertEqual(identify_intent("Explain the Dragon Break"), "search")


if __name__ == "__main__":
    unittest.main()
