"""Optional compatibility test for the experimental xmlstream package."""

import importlib.util
import unittest
from contextlib import redirect_stdout
from io import StringIO

from experiments.xml_parser_comparison.probe_xmlstream import main


@unittest.skipUnless(
    importlib.util.find_spec("xmlstream"),
    "Install experiments/xml_parser_comparison/requirements.txt to run this probe.",
)
class XMLStreamCompatibilityTests(unittest.TestCase):
    def test_candidate_preserves_required_mediawiki_page_fields(self):
        output = StringIO()
        with redirect_stdout(output):
            result = main()

        self.assertEqual(result, 0, output.getvalue())


if __name__ == "__main__":
    unittest.main()
