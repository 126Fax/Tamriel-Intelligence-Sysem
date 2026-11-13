"""Split a large MediaWiki XML export into valid, page-aligned bzip2 files.

The source file is never modified. Each output is a standalone MediaWiki XML
document containing the original root element, siteinfo and a whole-page
sequence. Page content, revisions, templates and metadata are retained.

Example:
    python -m tools.split_mediawiki_dump --input /path/to/dump.xml.bz2
    python -m tools.split_mediawiki_dump --input dump.xml --max-size-mb 90
"""

import argparse
import bz2
import gzip
import json
from pathlib import Path

from lxml import etree


TOOL_VERSION = "1.0"
DEFAULT_MAX_SIZE_MB = 90
XML_PARSER_OPTIONS = {
    "huge_tree": True,
    "resolve_entities": False,
    "no_network": True,
    "remove_comments": False,
}


def open_xml_source(path):
    """Open plain, gzip or bzip2 XML as a binary stream."""
    path = Path(path)
    suffixes = [suffix.lower() for suffix in path.suffixes]

    if suffixes[-1:] == [".bz2"]:
        return bz2.open(path, "rb")
    if suffixes[-1:] == [".gz"]:
        return gzip.open(path, "rb")
    return path.open("rb")


def output_directory_for(input_path):
    """Return a predictable output folder based on the source filename."""
    name = Path(input_path).name
    for ending in (".xml.bz2", ".xml.gz", ".xml"):
        if name.lower().endswith(ending):
            name = name[:-len(ending)]
            break
    return Path("data") / "processed" / name


class PartWriter:
    """Write one standalone MediaWiki XML part using bounded memory."""

    def __init__(self, path, root, siteinfo):
        self.path = Path(path)
        self.handle = bz2.open(self.path, "wb")
        self.xml_file = etree.xmlfile(self.handle, encoding="utf-8")
        self.xml_file.__enter__()
        self.xml_file.write_declaration()
        self.root_context = self.xml_file.element(
            root.tag,
            attrib=dict(root.attrib),
            nsmap=root.nsmap,
        )
        self.root_context.__enter__()
        self.xml_file.write(siteinfo)

    def write_page(self, page):
        self.xml_file.write(page)

    def close(self):
        if self.root_context is not None:
            self.root_context.__exit__(None, None, None)
            self.root_context = None
        if self.xml_file is not None:
            self.xml_file.__exit__(None, None, None)
            self.xml_file = None
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def split_mediawiki_dump(input_path, output_dir, max_size_mb=DEFAULT_MAX_SIZE_MB):
    """Split a MediaWiki dump at page boundaries and write a JSON manifest.

    The size limit is measured against the uncompressed XML representation.
    Compressed parts will normally be smaller. A single page larger than the
    requested limit is kept intact in its own part rather than being damaged.
    """
    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()

    if not input_path.is_file():
        raise FileNotFoundError(f"Input XML dump not found: {input_path}")
    if max_size_mb <= 0:
        raise ValueError("Maximum part size must be greater than zero.")

    max_size_bytes = int(max_size_mb * 1024 * 1024)
    output_dir.mkdir(parents=True, exist_ok=True)

    root = None
    siteinfo = None
    writer = None
    part_number = 0
    part_page_count = 0
    part_xml_bytes = 0
    total_pages = 0
    parts = []
    first_title = None
    last_title = None

    def start_part():
        nonlocal writer, part_number, part_page_count, part_xml_bytes
        nonlocal first_title, last_title

        part_number += 1
        part_page_count = 0
        part_xml_bytes = 0
        first_title = None
        last_title = None
        part_path = output_dir / f"part_{part_number:04d}.xml.bz2"
        writer = PartWriter(part_path, root, siteinfo)

    def finish_part():
        nonlocal writer

        if writer is None:
            return

        path = writer.path
        writer.close()
        parts.append({
            "file": path.name,
            "pages": part_page_count,
            "uncompressed_xml_bytes_estimate": part_xml_bytes,
            "compressed_bytes": path.stat().st_size,
            "first_title": first_title,
            "last_title": last_title,
        })
        writer = None

    try:
        with open_xml_source(input_path) as source:
            context = etree.iterparse(
                source,
                events=("start", "end"),
                **XML_PARSER_OPTIONS,
            )

            for event, element in context:
                if event == "start" and root is None:
                    root = element
                    continue

                if event != "end":
                    continue

                local_name = etree.QName(element).localname

                if local_name == "siteinfo" and siteinfo is None:
                    siteinfo = etree.fromstring(etree.tostring(element))
                    element.clear()
                    continue

                if local_name != "page":
                    continue

                if root is None or siteinfo is None:
                    raise ValueError(
                        "The XML does not contain a MediaWiki root and siteinfo "
                        "before its page elements."
                    )

                page_bytes = len(etree.tostring(element, encoding="utf-8"))

                if writer is None:
                    start_part()
                elif part_page_count and part_xml_bytes + page_bytes > max_size_bytes:
                    finish_part()
                    start_part()

                title = element.findtext(
                    f"{{{etree.QName(element).namespace}}}title"
                )
                writer.write_page(element)
                part_page_count += 1
                part_xml_bytes += page_bytes
                total_pages += 1

                if first_title is None:
                    first_title = title
                last_title = title

                element.clear()
                while element.getprevious() is not None:
                    del element.getparent()[0]

        finish_part()

    except Exception:
        if writer is not None:
            writer.close()
        raise

    if total_pages == 0:
        raise ValueError("No MediaWiki page elements were found in the XML dump.")

    manifest = {
        "format_version": 1,
        "tool_version": TOOL_VERSION,
        "source_file": input_path.name,
        "source_bytes": input_path.stat().st_size,
        "max_part_size_mb": max_size_mb,
        "size_measurement": "estimated uncompressed serialized page XML",
        "total_pages": total_pages,
        "part_count": len(parts),
        "parts": parts,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Split a MediaWiki XML dump into valid page-aligned files."
    )
    parser.add_argument("--input", required=True, help="XML, XML.GZ or XML.BZ2 dump.")
    parser.add_argument(
        "--output-dir",
        help="Output directory (defaults to data/processed/<dump-name>/).",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=DEFAULT_MAX_SIZE_MB,
        help=f"Approximate uncompressed size per part (default: {DEFAULT_MAX_SIZE_MB} MB).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else output_directory_for(args.input)
    manifest = split_mediawiki_dump(args.input, output_dir, args.max_size_mb)

    print("===== MEDIAWIKI DUMP SPLIT =====")
    print(f"Source: {manifest['source_file']}")
    print(f"Pages: {manifest['total_pages']:,}")
    print(f"Parts: {manifest['part_count']:,}")
    print(f"Output: {output_dir}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    for part in manifest["parts"]:
        print(
            f"  {part['file']}: {part['pages']:,} pages, "
            f"{part['compressed_bytes'] / (1024 * 1024):.2f} MB compressed"
        )


if __name__ == "__main__":
    main()
