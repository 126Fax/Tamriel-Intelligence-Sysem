import unittest
from unittest.mock import patch

from top_down.random_fact import (
    answer_random_fact,
    choose_random_fact,
    format_random_fact,
    is_random_fact_question,
)
from top_down.question_analyser import analyse_question, answer_question


class RandomFactTests(unittest.TestCase):
    def setUp(self):
        import top_down.random_fact as random_fact
        random_fact._remaining_facts = []
        random_fact._last_fact = None

    def test_recognises_random_fact_requests(self):
        for question in (
            "Random fact",
            "Tell me a random fact",
            "Give me a random lore fact",
            "Surprise me with a fact",
        ):
            with self.subTest(question=question):
                self.assertTrue(is_random_fact_question(question))

    def test_does_not_misclassify_other_questions(self):
        self.assertFalse(is_random_fact_question("Where does Vivec live?"))

    def test_analyser_assigns_random_fact_intent(self):
        self.assertEqual(analyse_question("Tell me a random fact")["intent"], "random_fact")

    def test_selects_each_fact_before_repeating(self):
        facts = [
            {"subject": "A", "relationship": "is", "object": "one"},
            {"subject": "B", "relationship": "is", "object": "two"},
            {"subject": "C", "relationship": "is", "object": "three"},
        ]
        selected = [choose_random_fact(facts) for _ in range(3)]
        self.assertEqual(len({fact["subject"] for fact in selected}), 3)

    def test_formats_fact_and_optional_source(self):
        fact = {
            "subject": "Skyrim",
            "relationship": "is a province of",
            "object": "the Empire",
            "source_page": "Skyrim",
        }
        answer = format_random_fact(fact)
        self.assertIn("Skyrim is a province of the Empire.", answer)
        self.assertIn("Source page: Skyrim", answer)
        self.assertIn("extracted candidate fact", answer)

    def test_returns_helpful_message_when_no_facts_exist(self):
        with patch("top_down.random_fact.load_explicit_facts", return_value=[]):
            answer = answer_random_fact("Tell me a random fact")
        self.assertIn("do not have any structured facts", answer)

    def test_answer_question_routes_random_fact(self):
        fact = {"subject": "Morrowind", "relationship": "is", "object": "a province"}
        with patch("top_down.random_fact.load_explicit_facts", return_value=[fact]):
            answer = answer_question("Tell me a random fact")
        self.assertIn("Morrowind is a province.", answer)


if __name__ == "__main__":
    unittest.main()
