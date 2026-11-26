"""Retrieve matching triples from the project's JSON knowledge base."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base.json"
REQUIRED_FIELDS = ("subject", "relationship", "object")


class KnowledgeBaseError(ValueError):
    """Raised when the knowledge-base file is missing or malformed."""


def _normalise(value):
    return " ".join(str(value).casefold().split())


def load_knowledge_base(path=DEFAULT_KNOWLEDGE_BASE):
    """Load and validate a list of subject/relationship/object records."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except FileNotFoundError as exc:
        raise KnowledgeBaseError(f"Knowledge base not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseError(f"Knowledge base contains invalid JSON: {path}") from exc

    if not isinstance(records, list):
        raise KnowledgeBaseError("Knowledge base must contain a JSON list.")

    for index, record in enumerate(records):
        if not isinstance(record, dict) or any(
            not isinstance(record.get(field), str) or not record[field].strip()
            for field in REQUIRED_FIELDS
        ):
            raise KnowledgeBaseError(
                f"Record {index} must contain non-empty subject, relationship and object strings."
            )
    return records


def retrieve_facts(analysis, facts=None):
    """Return facts matching the interpreted subject, object and relationship.

    If the analyser cannot identify a specific relation, return no results
    rather than guessing which facts might answer the question.
    """
    if facts is None:
        facts = load_knowledge_base()

    relationship = analysis.get("relationship")
    subject_hint = analysis.get("subject_hint")
    object_hint = analysis.get("object_hint")
    intent = analysis.get("intent")

    if not relationship:
        return []

    matches = []
    for fact in facts:
        if _normalise(fact["relationship"]) != _normalise(relationship):
            continue
        if intent == "find_subjects":
            if object_hint and _normalise(fact["object"]) == _normalise(object_hint):
                matches.append(fact)
            elif not object_hint and subject_hint and _normalise(fact["subject"]) == _normalise(subject_hint):
                matches.append(fact)
        elif intent == "find_object":
            if subject_hint and _normalise(fact["subject"]) == _normalise(subject_hint):
                matches.append(fact)
    return matches
