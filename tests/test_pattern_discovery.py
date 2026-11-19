"""Tests for explainable bottom-up sentence-pattern discovery."""

import unittest

from bottom_up.pattern_discovery import (
    VARIABLE,
    discover_shared_patterns,
    find_specialisations,
)


class SharedPatternTests(unittest.TestCase):
    def test_finds_shared_structure_in_same_length_sentences(self):
        sentences = [
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
            "Cyrodiil is a province of the Empire",
        ]
        patterns = discover_shared_patterns(sentences)
        expected = f"{VARIABLE} is a province of the Empire"
        self.assertIn(expected, patterns)
        details = patterns[expected]
        self.assertCountEqual(details["words"], ["Skyrim", "Morrowind", "Cyrodiil"])
        self.assertCountEqual(details["sentences"], sentences)
        self.assertEqual(details["support"], 3)

    def test_multi_word_name_is_one_variable_value(self):
        sentences = [
            "Skyrim is a province of the Empire",
            "High Rock is a province of the Empire",
            "Morrowind is a province of the Empire",
        ]
        details = discover_shared_patterns(sentences)[
            f"{VARIABLE} is a province of the Empire"
        ]
        self.assertIn("High Rock", details["words"])
        self.assertIn(("High Rock",), details["values"])

    def test_variables_in_middle_and_at_end_keep_separate_values(self):
        sentences = [
            "The capital of Skyrim is Solitude",
            "The capital of High Rock is Daggerfall",
            "The capital of Morrowind is Vivec",
        ]
        patterns = discover_shared_patterns(sentences)
        expected = f"The capital of {VARIABLE} is {VARIABLE}"
        self.assertIn(expected, patterns)
        values = patterns[expected]["values"]
        self.assertIn(("Skyrim", "Solitude"), values)
        self.assertIn(("High Rock", "Daggerfall"), values)
        self.assertIn(("Morrowind", "Vivec"), values)

    def test_pattern_below_minimum_support_is_rejected(self):
        sentences = [
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
        ]
        self.assertNotIn(
            f"{VARIABLE} is a province of the Empire",
            discover_shared_patterns(sentences, minimum_support=3),
        )

    def test_pattern_exactly_at_minimum_support_is_kept(self):
        sentences = [
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
            "Cyrodiil is a province of the Empire",
        ]
        self.assertIn(
            f"{VARIABLE} is a province of the Empire",
            discover_shared_patterns(sentences, minimum_support=3),
        )

    def test_sentences_with_almost_nothing_in_common_give_no_pattern(self):
        sentences = [
            "The dragon guards the ancient temple",
            "A merchant sells expensive weapons",
            "Several soldiers patrol the northern road",
        ]
        self.assertEqual(discover_shared_patterns(sentences), {})

    def test_general_pattern_and_specialisations_are_both_kept(self):
        sentences = [
            "Skyrim is a province of Tamriel",
            "Morrowind is a province of Tamriel",
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
        ]
        patterns = discover_shared_patterns(sentences)
        self.assertIn(f"{VARIABLE} is a province of {VARIABLE}", patterns)
        self.assertIn(f"{VARIABLE} is a province of Tamriel", patterns)
        self.assertIn(f"{VARIABLE} is a province of the Empire", patterns)

    def test_specialisation_relationship_is_identified(self):
        sentences = [
            "Skyrim is a province of Tamriel",
            "Morrowind is a province of Tamriel",
            "Skyrim is a province of the Empire",
            "Morrowind is a province of the Empire",
        ]
        relationships = find_specialisations(discover_shared_patterns(sentences))
        pairs = {
            (item["general_pattern"], item["specialised_pattern"])
            for item in relationships
        }
        general = f"{VARIABLE} is a province of {VARIABLE}"
        self.assertIn((general, f"{VARIABLE} is a province of Tamriel"), pairs)
        self.assertIn((general, f"{VARIABLE} is a province of the Empire"), pairs)


if __name__ == "__main__":
    unittest.main()
