import bz2
from lxml import etree

XML_NAMESPACE = "{http://www.mediawiki.org/xml/export-0.10/}"


def read_namespaces(file_path):
    with bz2.open(file_path, "rb") as dump_file:
        context = etree.iterparse(
            dump_file,
            events=("end",),
            tag=f"{XML_NAMESPACE}siteinfo",
            huge_tree=True,
            resolve_entities=False,
            no_network=True,
        )
        for event, siteinfo in context:
            namespaces = siteinfo.find(f"{XML_NAMESPACE}namespaces")
            namespace_map = {}
            for namespace in namespaces:
                namespace_id = int(namespace.get("key"))
                namespace_name = namespace.text or ""
                namespace_map[namespace_id] = namespace_name
            return namespace_map
