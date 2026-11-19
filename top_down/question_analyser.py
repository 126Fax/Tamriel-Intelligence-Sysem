"""Rule-based interpretation of a broad range of lore questions.

The analyser extracts intent and search hints; retrieval is handled separately.
It is intentionally explainable and never treats a keyword match as proof.
"""
import re


def normalise_question(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")
    return re.sub(r"\s+", " ", question.strip()).casefold()


def _clean(value):
    return re.sub(r"^[\s,;:]+|[?!.\s,;:]+$", "", value).strip()


def identify_intent(question):
    q = normalise_question(question)
    if re.match(r"^how many\b", q):
        return "count"
    if re.match(r"^(?:what|who|where|when|which|tell me about|describe)\b", q):
        return "lookup"
    return "search"


def identify_relationship(question):
    q = normalise_question(question)
    rules = (
        (r"\b(?:province|provinces)\b", "province"),
        (r"\b(?:continent|continents)\b", "continent"),
        (r"\b(?:farmer|farmers|occupation|occupations)\b", "occupation"),
        (r"\b(?:live|lives|living)\b", "lives in"),
        (r"\b(?:rule|rules|ruled by)\b", "rules"),
        (r"\b(?:capital|capitals)\b", "capital"),
        (r"\b(?:located|location)\b", "located in"),
    )
    for pattern, relationship in rules:
        if re.search(pattern, q):
            return relationship
    return None


def analyse_question(question):
    original = question
    q = normalise_question(question)
    intent = identify_intent(q)
    result = {
        "original_question": original,
        "normalised_question": q,
        "intent": intent,
        "search_term": _clean(q),
        "relationship": identify_relationship(q),
        "subject_hint": None,
        "object_hint": None,
        "count_target": None,
    }

    if intent == "count":
        match = re.match(
            r"^how many (.+?)(?: are there| exist| do we know| are known)?[?!.]*$",
            q,
        )
        if match:
            target = _clean(match.group(1))
            target = re.sub(r"^(?:of )", "", target)
            result["count_target"] = target
            result["search_term"] = target
        return result

    patterns = (
        r"^(?:what do you know about|what can you tell me about|tell me about|describe|explain) (.+?)[?!.]*$",
        r"^(?:what|which) are (?:the )?(.+?)[?!.]*$",
        r"^(?:what|who|where|when) is (?:the )?(.+?)[?!.]*$",
        r"^who was (?:the )?(.+?)[?!.]*$",
        r"^where is (?:the )?(.+?)[?!.]*$",
        r"^which (.+?)[?!.]*$",
    )
    for pattern in patterns:
        match = re.match(pattern, q)
        if match:
            result["subject_hint"] = _clean(match.group(1))
            result["search_term"] = result["subject_hint"]
            break

    match = re.match(r"^(?:which|what) (.+?) belong to (?:the )?(.+?)[?!.]*$", q)
    if match:
        result.update(intent="find_subjects", relationship="province",
                      object_hint=_clean(match.group(2)),
                      search_term=_clean(match.group(2)))
    match = re.match(r"^where do (.+?) live[?!.]*$", q)
    if not match:
        match = re.match(r"^where does (.+?) live[?!.]*$", q)
    if match:
        result.update(intent="find_object", relationship="lives in",
                      subject_hint=_clean(match.group(1)),
                      search_term=_clean(match.group(1)))
    match = re.match(r"^who rules (?:the )?(.+?)[?!.]*$", q)
    if match:
        result.update(intent="find_subjects", relationship="rules",
                      object_hint=_clean(match.group(1)),
                      search_term=_clean(match.group(1)))
    return result


def extract_search_term(question):
    return analyse_question(question)["search_term"]
