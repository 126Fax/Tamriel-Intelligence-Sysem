import unittest

from top_down.question_analyser import analyse_question, identify_intent


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

    def test_unknown_question_is_sent_to_search_not_crashed(self):
        self.assertEqual(identify_intent("Explain the Dragon Break"), "search")


if __name__ == "__main__":
    unittest.main()
