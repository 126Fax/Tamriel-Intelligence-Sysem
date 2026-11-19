"""Explainable first-pass review of bottom-up candidate facts.

This prototype is deliberately rule-based. It never invents or rewrites a fact.
It classifies each input record as approved, rejected, or needs_review and keeps
the complete original record and reasons for that decision.
"""
import json
import re
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "knowledge_base.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "cleaner" / "cleaner_results.json"
REQUIRED_FIELDS = ("subject", "relationship", "object", "evidence")

RELATIONSHIP_EVIDENCE_PATTERNS = {
    "province": re.compile(
        r"\b{subject}\s+is\s+(?:a|an)\s+province\s+of\s+{object}\b",
        re.IGNORECASE,
    ),
    "lives in": re.compile(
        r"\b{subject}\s+lives?\s+in\s+{object}\b",
        re.IGNORECASE,
    ),
    "located in": re.compile(
        r"\b{subject}\s+is\s+located\s+in\s+{object}\b",
        re.IGNORECASE,
    ),
}

FRAGMENT_STARTS = {
    "and", "but", "or", "because", "although", "after", "before",
    "while", "when", "if", "who", "which", "that", "he", "she",
    "they", "it", "we", "i", "you", "all", "the", "a", "an",
}
FRAGMENT_MARKERS = (
    " is ", " are ", " was ", " were ", " who ", " which ",
    " that ", " used to ", " wishing to ", " decided to ",
)
PRONOUN_OBJECTS = {"it", "they", "them", "he", "she", "him", "her", "this", "that"}


def _normalise(value):
    return " ".join(str(value).casefold().split())


def _has_evidence(record):
    """Check whether the supplied evidence explicitly expresses the triple."""
    relationship = _normalise(record["relationship"])
    pattern = RELATIONSHIP_EVIDENCE_PATTERNS.get(relationship)
    if pattern is None:
        return None

    subject = re.escape(" ".join(record["subject"].split()))
    obj = re.escape(" ".join(record["object"].split()))
    expression = pattern.pattern.format(subject=subject, object=obj)
    return re.search(expression, record["evidence"], re.IGNORECASE) is not None


def review_fact(record):
    """Return a review result without changing the original candidate fields."""
    if not isinstance(record, dict):
        return {"status": "rejected", "reasons": ["Record is not a JSON object."],
                "fact": record}

    missing = [
        field for field in REQUIRED_FIELDS
        if not isinstance(record.get(field), str) or not record[field].strip()
    ]
    if missing:
        return {
            "status": "rejected",
            "reasons": ["Missing or empty required fields: " + ", ".join(missing)],
            "fact": record,
        }

    subject = " ".join(record["subject"].split()).strip(" .,:;!?")
    obj = " ".join(record["object"].split()).strip(" .,:;!?")
    relationship = _normalise(record["relationship"])
    subject_words = subject.split()
    reasons = []

    if _normalise(subject) == _normalise(obj):
        return {"status": "rejected", "reasons": ["Subject and object are identical."],
                "fact": record}

    first_word = subject_words[0].casefold() if subject_words else ""
    if first_word in FRAGMENT_STARTS:
        return {
            "status": "rejected",
            "reasons": [f"Subject begins with '{subject_words[0]}', suggesting a sentence fragment."],
            "fact": record,
        }

    lowered_subject = f" {subject.casefold()} "
    marker = next((item.strip() for item in FRAGMENT_MARKERS if item in lowered_subject), None)
    if marker:
        return {
            "status": "rejected",
            "reasons": [f"Subject contains clause marker '{marker}', suggesting it is not an entity name."],
            "fact": record,
        }

    if len(subject_words) > 7:
        return {
            "status": "rejected",
            "reasons": ["Subject is longer than seven words and is likely a sentence fragment."],
            "fact": record,
        }

    if _normalise(obj) in PRONOUN_OBJECTS:
        return {
            "status": "rejected",
            "reasons": ["Object is a pronoun rather than an identifiable place or entity."],
            "fact": record,
        }

    if relationship not in RELATIONSHIP_EVIDENCE_PATTERNS:
        return {
            "status": "needs_review",
            "reasons": [f"No evidence-checking rule exists for relationship '{record['relationship']}'."],
            "fact": record,
        }

    if len(subject_words) > 5:
        reasons.append("Subject is unusually long and should be checked as a possible entity name.")

    evidence_matches = _has_evidence({
        "subject": subject, "object": obj, "relationship": relationship,
        "evidence": record["evidence"],
    })
    if evidence_matches is False:
        reasons.append("Evidence does not explicitly support the extracted subject–relationship–object triple.")
    elif evidence_matches is None:
        reasons.append("Evidence could not be checked automatically.")

    if reasons:
        return {"status": "needs_review", "reasons": reasons, "fact": record}

    return {
        "status": "approved",
        "reasons": ["Required fields are valid and the evidence explicitly supports the extracted relationship."],
        "fact": record,
    }


def clean_knowledge_base(records):
    """Review a list of candidates and return a complete, auditable report."""
    if not isinstance(records, list):
        raise ValueError("Knowledge base must contain a JSON list of candidate facts.")

    results = [review_fact(record) for record in records]
    counts = Counter(result["status"] for result in results)
    return {
        "cleaner_version": "0.1.0",
        "review_policy": "rule_based_evidence_checks",
        "summary": {
            "total": len(results),
            "approved": counts["approved"],
            "rejected": counts["rejected"],
            "needs_review": counts["needs_review"],
        },
        "results": results,
    }


def clean_file(input_path=DEFAULT_INPUT, output_path=DEFAULT_OUTPUT):
    """Read candidate JSON and write an auditable cleaner report."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    with input_path.open("r", encoding="utf-8") as source:
        records = json.load(source)

    report = clean_knowledge_base(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return report
