import unittest

from bottom_up.province_catalog import audit_discovered_provinces, load_provinces


class ProvinceCatalogTests(unittest.TestCase):
    def test_catalog_contains_nine_traditional_provinces(self):
        provinces = load_provinces()
        self.assertEqual(len(provinces), 9)
        self.assertIn("High Rock", provinces)
        self.assertIn("Summerset Isles", provinces)

    def test_audit_separates_discovered_missing_and_unexpected(self):
        facts = [
            {"subject": "Skyrim", "relationship": "province of", "object": "Tamriel"},
            {"subject": "Murkmire", "relationship": "province", "object": "Black Marsh"},
        ]
        report = audit_discovered_provinces(facts)
        self.assertEqual(report["discovered_count"], 1)
        self.assertEqual(report["missing"], [
            "Morrowind", "Cyrodiil", "Hammerfell", "High Rock",
            "Valenwood", "Elsweyr", "Black Marsh", "Summerset Isles",
        ])
        self.assertEqual(report["unexpected_candidates"][0]["subject"], "Murkmire")


if __name__ == "__main__":
    unittest.main()
