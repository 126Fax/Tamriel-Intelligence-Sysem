"""Rule-based interpretation of natural-language questions.

This is deliberately a small, explainable first prototype. It does not use an
LLM: it recognises a handful of question patterns and turns them into
structured retrieval hints.
"""

import re


def normalise_question(question):
    """Trim and case-fold a question, rejecting empty input."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")
    return re.sub(r"\s+", " ", question.strip()).casefold()


def identify_intent(question):
    """Return whether the question asks for subjects or an object's value."""
    q = normalise_question(question)
    if re.match(r"^(which|what)\b", q):
        return "find_subjects"
    if re.match(r"^who\b", q):
        return "find_subjects"
    if re.match(r"^(where|when)\b", q):
        return "find_object"
    return "unknown"


def identify_relationship(question):
    """Map common wording to the relationship labels used in the knowledge base."""
    q = normalise_question(question)
    if re.search(r"\b(belong to|part of|provinces? of)\b", q):
        return "province"
    if re.search(r"\b(live|lives|living)\b", q):
        return "lives in"
    if re.search(r"\brules?\b", q):
        return "rules"
    return None


def _clean_term(value):
    return re.sub(r"^[\s,;:]+|[?!.\s,;:]+$", "", value).strip()


def analyse_question(question):
    """Return a structured interpretation suitable for knowledge retrieval."""
    original = question
    q = normalise_question(question)
    result = {
        "original_question": original,
        "normalised_question": q,
        "intent": identify_intent(q),
        "search_term": _clean_term(q),
        "relationship": identify_relationship(q),
        "subject_hint": None,
        "object_hint": None,
    }

    match = re.match(r"^(?:which|what) (.+?) belong to (?:the )?(.+?)[?.!]*$", q)
    if match:
        result.update(intent="find_subjects", relationship="province",
                      object_hint=_clean_term(match.group(2)))
        result["search_term"] = result["object_hint"]
        return result

    match = re.match(r"^where do (.+?) live[?.!]*$", q)
    if not match:
        match = re.match(r"^where does (.+?) live[?.!]*$", q)
    if match:
        result.update(intent="find_object", relationship="lives in",
                      subject_hint=_clean_term(match.group(1)))
        result["search_term"] = result["subject_hint"]
        return result

    match = re.match(r"^who rules (?:the )?(.+?)[?.!]*$", q)
    if match:
        result.update(intent="find_subjects", relationship="rules",
                      object_hint=_clean_term(match.group(1)))
        result["search_term"] = result["object_hint"]
        return result

    return result


def extract_search_term(question):
    """Compatibility helper returning the useful target term where recognised."""
    return analyse_question(question)["search_term"]


if __name__ == "__main__":
    for example in (
        "Which provinces belong to the Empire?",
        "Where do dragons live?",
        "WHO RULES SKYRIM?",
    ):
        print("\n===== QUESTION ANALYSIS =====")
        for key, value in analyse_question(example).items():
            print(f"{key}: {value}")
