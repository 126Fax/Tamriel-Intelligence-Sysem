"""Experimental extraction of race, occupation and book observations.

This module is deliberately separate from bottom_up.full_pipeline. It produces
candidate observations with explicit provenance; it does not write to the
production database or knowledge_base.json.
"""
import re

import mwparserfromhell


FIELD_TYPES = {
    "race": "race",
    "species": "race",
    "occupation": "occupation",
    "profession": "occupation",
    "job": "occupation",
    "book": "book",
    "books": "book",
    "book title": "book",
    "book titles": "book",
    "book name": "book",
    "associated book": "book",
    "associated books": "book",
}


def _normalise_field_name(value):
    return re.sub(r"\s+", " ", str(value).replace("_", " ")).strip().casefold()


def _clean_value(value):
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip(" \t\r\n.,;:|")


def _observation(entity_type, subject, value, evidence, source_page_id,
                 source_page, extraction_method, provenance):
    return {
        "entity_type": entity_type,
        "subject": subject,
        "value": value,
        "source_page_id": source_page_id,
        "source_page": source_page,
        "evidence": evidence[:2000],
        "extraction_method": extraction_method,
        "provenance": dict(provenance),
    }


def extract_uesp_observations(page, dump_name):
    """Extract conservative candidates from one imported UESP page.

    Only explicit template fields are interpreted. Generic fields such as
    'title' are not assumed to mean a book, because that would create false
    positives across unrelated templates.
    """
    required = {"page_id", "title", "text"}
    missing = required.difference(page)
    if missing:
        raise ValueError(f"Page is missing required fields: {sorted(missing)}")

    provenance = {
        "source_type": "uesp",
        "source_id": dump_name,
        "mod_id": None,
    }
    page_id = int(page["page_id"])
    title = str(page["title"]).strip()
    wikicode = mwparserfromhell.parse(page.get("text") or "")
    observations = []
    seen = set()

    def add(entity_type, value, evidence, method):
        value = _clean_value(value)
        if not value:
            return
        item = _observation(
            entity_type, title, value, evidence, page_id, title, method,
            provenance,
        )
        key = (item["entity_type"], item["subject"].casefold(),
               item["value"].casefold(), item["evidence"])
        if key not in seen:
            seen.add(key)
            observations.append(item)

    for template in wikicode.filter_templates():
        template_name = _normalise_field_name(str(template.name))
        template_evidence = str(template)
        is_book_template = "book" in template_name

        if is_book_template:
            # A book-specific template is evidence that this page describes a
            # book. Do not infer this from a generic 'title' parameter alone.
            add("book", title, template_evidence, "book_template_v1")

        for parameter in template.params:
            field_name = _normalise_field_name(str(parameter.name))
            entity_type = FIELD_TYPES.get(field_name)
            if entity_type is None:
                continue
            value = parameter.value.strip_code(
                normalize=True, collapse=True
            ).strip()
            add(
                entity_type, value, template_evidence,
                "template_field_v1",
            )

    return observations


def make_external_observation(entity_type, subject, value, evidence,
                              source_type, source_id, mod_id=None):
    """Create a user- or mod-supplied observation without disguising its origin.

    source_id should identify the submitted source or package, not a person's
    private identity. mod_id is required for mod observations.
    """
    allowed_types = {"race", "occupation", "book"}
    if entity_type not in allowed_types:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    if source_type not in {"user", "mod"}:
        raise ValueError("External source_type must be 'user' or 'mod'.")
    if not str(subject).strip() or not str(value).strip():
        raise ValueError("Subject and value must not be empty.")
    if not str(source_id).strip():
        raise ValueError("source_id must not be empty.")
    if source_type == "mod" and not (mod_id and str(mod_id).strip()):
        raise ValueError("mod_id is required for mod observations.")

    provenance = {
        "source_type": source_type,
        "source_id": str(source_id).strip(),
        "mod_id": str(mod_id).strip() if mod_id else None,
    }
    return _observation(
        entity_type, str(subject).strip(), str(value).strip(),
        str(evidence), None, None, f"{source_type}_provided_v1", provenance,
    )


def group_observations_by_source(observations):
    """Group candidates without merging facts from different origins."""
    grouped = {}
    for item in observations:
        provenance = item["provenance"]
        key = (
            provenance["source_type"],
            provenance["source_id"],
            provenance.get("mod_id"),
        )
        grouped.setdefault(key, []).append(item)
    return grouped
