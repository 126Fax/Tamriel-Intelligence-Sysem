import unittest

from bottom_up.full_pipeline import extract_candidate_facts


class ProvinceExtractionTests(unittest.TestCase):
    def test_extracts_less_common_nine_provinces_sentence(self):
        facts = extract_candidate_facts(
            "Skyrim is one of the nine provinces of Tamriel.",
            10,
            "Test page",
        )
        province_facts = [
            fact for fact in facts
            if fact["relationship"] == "province of"
        ]
        self.assertEqual(len(province_facts), 1)
        self.assertEqual(province_facts[0]["subject"], "Skyrim")
        self.assertEqual(province_facts[0]["object"], "Tamriel")
        self.assertIn("one of the nine provinces", province_facts[0]["evidence"])

    def test_does_not_promote_unrelated_place_as_province(self):
        facts = extract_candidate_facts(
            "Murkmire is a region of Black Marsh.",
            11,
            "Test page",
        )
        self.assertFalse(any(
            fact["relationship"] == "province of" for fact in facts
        ))


if __name__ == "__main__":
    unittest.main()
