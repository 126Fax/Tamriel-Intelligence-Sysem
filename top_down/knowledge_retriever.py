"""Retrieve matching facts from the project's JSON knowledge base."""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "knowledge_base.json"


def load_knowledge_base(path=KNOWLEDGE_BASE_PATH):
    """Load and validate the JSON list of subject-relationship-object facts."""
    with open(path, "r", encoding="utf-8") as knowledge_file:
        records = json.load(knowledge_file)

    if not isinstance(records, list):
        raise ValueError("The knowledge base must contain a JSON list.")

    required_fields = ("subject", "relationship", "object")

    for index, record in enumerate(records):
        if not isinstance(record, dict) or any(
            not isinstance(record.get(field), str) or not record[field].strip()
            for field in required_fields
        ):
            raise ValueError(
                f"Knowledge-base record {index} must contain non-empty "
                "subject, relationship and object strings."
            )

    return records


def find_entities_in_question(question, records):
    """Find known subject/object names mentioned in the question.

    Longer names are checked first so that names containing other names are
    not accidentally split into multiple matches.
    """
    normalised = question.casefold()
    known_entities = {
        value
        for record in records
        for value in (record["subject"], record["object"])
    }

    matches = []
    for entity in sorted(known_entities, key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(entity.casefold())}(?!\w)"
        if re.search(pattern, normalised):
            matches.append(entity)

    return matches


def retrieve_facts(analysis, records=None):
    """Return facts relevant to an analysed question.

    If no records are supplied, the project's knowledge_base.json is loaded.
    The function returns an empty list when the knowledge base has no match.
    """
    if records is None:
        records = load_knowledge_base()

    question = analysis["normalised_question"]
    relationship = analysis.get("relationship")
    entities = find_entities_in_question(question, records)

    if relationship:
        related = [
            record for record in records
            if record["relationship"].casefold() == relationship.casefold()
        ]

        if entities:
            entity_keys = {entity.casefold() for entity in entities}
            matching = [
                record for record in related
                if record["subject"].casefold() in entity_keys
                or record["object"].casefold() in entity_keys
            ]
            return matching

        return related

    if entities:
        entity_keys = {entity.casefold() for entity in entities}
        return [
            record for record in records
            if record["subject"].casefold() in entity_keys
            or record["object"].casefold() in entity_keys
        ]

    return []


if __name__ == "__main__":
    print(f"Loaded {len(load_knowledge_base())} knowledge-base facts.")
