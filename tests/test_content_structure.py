"""Tests for wiki-markup and structured-content analysis."""

import unittest

from src.analysis.content_structure import (
    analyse_content_structure,
    analyse_json,
    analyse_template_parameters,
    analyse_template_relationships,
)


class ContentStructureTests(unittest.TestCase):
    def test_json_analysis_handles_objects_lists_and_scalars(self):
        self.assertEqual(
            analyse_json('{"name": "Skyrim", "year": "4E 201"}'),
            {"is_valid_json": True, "json_data_type": "dict", "json_entry_count": 2},
        )
        self.assertEqual(
            analyse_json('["Skyrim", "Morrowind"]')["json_entry_count"], 2
        )
        self.assertIsNone(analyse_json('"Skyrim"')["json_entry_count"])

    def test_invalid_json_is_reported_without_raising(self):
        self.assertEqual(
            analyse_json("{not json"),
            {"is_valid_json": False, "json_data_type": None, "json_entry_count": None},
        )

    def test_wiki_markup_counts_templates_links_headings_and_tags(self):
        text = (
            "{{Infobox|name=Skyrim|date={{Year|4E 201}}}} "
            "[[Skyrim|the north]] [[Empire]] "
            "[https://example.com external] "
            chr(10) + "== History ==" + chr(10) + "<ref>Source</ref>"
        )
        result = analyse_content_structure(text)

        self.assertEqual(result["template_count"], 2)
        self.assertEqual(result["template_names"], {"Infobox": 1, "Year": 1})
        self.assertEqual(result["wikilink_count"], 2)
        self.assertEqual(result["link_destinations"], {"Skyrim": 1, "Empire": 1})
        self.assertEqual(result["link_details"][0]["display_text"], "the north")
        self.assertEqual(result["external_link_count"], 1)
        self.assertEqual(result["heading_count"], 1)
        self.assertEqual(result["tag_names"], {"ref": 1})

    def test_template_parameter_analysis_counts_named_and_positional_parameters(self):
        result = analyse_template_parameters(
            "{{Infobox|name=Skyrim|region=North|region=Tamriel}} {{Year|4E 201}}"
        )
        self.assertEqual(result["Infobox"], {"name": 1, "region": 2})
        self.assertEqual(result["Year"], {"1": 1})

    def test_nested_template_relationship_is_detected(self):
        result = analyse_template_relationships(
            "{{Infobox|date={{Year|4E 201}}|other={{Citation}}}}"
        )
        self.assertEqual(result, {"Infobox": {"Year": 1, "Citation": 1}})


if __name__ == "__main__":
    unittest.main()
