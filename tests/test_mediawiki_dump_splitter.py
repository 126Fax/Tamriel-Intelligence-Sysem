import bz2
import tempfile
import unittest
from pathlib import Path

from lxml import etree

from tools.split_mediawiki_dump import split_mediawiki_dump


MEDIAWIKI_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/" version="0.10" xml:lang="en">
  <siteinfo>
    <sitename>Example Wiki</sitename>
    <namespaces><namespace key="0" /></namespaces>
  </siteinfo>
  <page><title>First</title><ns>0</ns><id>1</id>
    <revision><id>11</id><text>First page with {{Template|x=y}}</text></revision>
  </page>
  <page><title>Second</title><ns>0</ns><id>2</id>
    <revision><id>22</id><text>Second page with [[A link]]</text></revision>
  </page>
  <page><title>Third</title><ns>0</ns><id>3</id>
    <revision><id>33</id><text>Third page</text></revision>
  </page>
</mediawiki>
"""


class TestMediaWikiDumpSplitter(unittest.TestCase):
    def test_splits_only_between_complete_pages_and_preserves_content(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.xml.bz2"
            output = root / "parts"

            source.write_bytes(bz2.compress(MEDIAWIKI_XML))
            manifest = split_mediawiki_dump(
                source,
                output,
                max_size_mb=0.0002,
            )

            self.assertEqual(manifest["total_pages"], 3)
            self.assertGreaterEqual(manifest["part_count"], 2)
            self.assertTrue((output / "manifest.json").is_file())

            recovered_titles = []
            recovered_text = []

            for part in sorted(output.glob("*.xml.bz2")):
                with bz2.open(part, "rb") as stream:
                    tree = etree.parse(stream)

                namespace = {"mw": "http://www.mediawiki.org/xml/export-0.10/"}
                self.assertIsNotNone(tree.find(".//mw:siteinfo", namespace))
                self.assertEqual(
                    tree.getroot().get("{http://www.w3.org/XML/1998/namespace}lang"),
                    "en",
                )

                for page in tree.findall(".//mw:page", namespace):
                    recovered_titles.append(page.findtext("mw:title", namespaces=namespace))
                    recovered_text.append(page.findtext(".//mw:text", namespaces=namespace))

            self.assertEqual(recovered_titles, ["First", "Second", "Third"])
            self.assertIn("{{Template|x=y}}", recovered_text[0])
            self.assertIn("[[A link]]", recovered_text[1])


if __name__ == "__main__":
    unittest.main()
