"""Backward-compatible import for the namespace reader.

Use :mod:`src.ingestion.namespaces` in new code.
"""

from src.ingestion.namespaces import XML_NAMESPACE, read_namespaces

__all__ = ["XML_NAMESPACE", "read_namespaces"]
