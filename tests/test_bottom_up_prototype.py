"""Tests for the current explainable, hardcoded bottom-up prototype."""

import unittest

from bottom_up.bottom_up_ai_prototype import (
    assign_pattern_meanings,
    discover_phrases,
    discover_province_relationships,
    discover_relationships,
    discover_shared_patterns,
    discover_word_patterns,
    rank_patterns,
)


class BottomUpPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.pages = [
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
            "Dragons live in Skyrim",
        ]

    def test_word_frequency_counts_repeated_terms(self):
        counts = discover_word_patterns(self.pages)
        self.assertEqual(counts["skyrim"], 2)
        self.assertEqual(counts["province"], 2)

    def test_rank_patterns_orders_highest_frequency_first(self):
        self.assertEqual(rank_patterns({"low": 1, "high": 3, "middle": 2})[0], ("high", 3))

    def test_phrase_discovery_counts_adjacent_words(self):
        phrases = discover_phrases(self.pages)
        self.assertEqual(phrases["province of"], 2)

    def test_province_relationships_extract_subjects(self):
        relationships = discover_province_relationships(self.pages)
        self.assertEqual(
            relationships,
            [
                {"subject": "Skyrim", "relationship": "province", "object": "Empire"},
                {"subject": "Morrowind", "relationship": "province", "object": "Empire"},
            ],
        )

    def test_configured_relationship_pattern_extracts_dragon_habitat(self):
        self.assertEqual(
            discover_relationships(self.pages),
            [{"subject": "Dragons", "relationship": "lives in", "object": "Skyrim"}],
        )

    def test_shared_sentence_pattern_can_be_labelled(self):
        patterns = discover_shared_patterns(self.pages[:2])
        assign_pattern_meanings(patterns)
        self.assertIn("[VARIABLE] is a province of the Empire", patterns)
        self.assertEqual(
            patterns["[VARIABLE] is a province of the Empire"]["meaning"],
            "province",
        )
        self.assertEqual(
            len(patterns["[VARIABLE] is a province of the Empire"]["sentences"]), 2
        )


if __name__ == "__main__":
    unittest.main()
