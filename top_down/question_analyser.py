"""Understand simple natural-language questions about Elder Scrolls lore.

This module deliberately uses transparent rules rather than a trained language
model. It converts a question into a small structure that the retriever can use.
"""

import re


def normalise_question(question):
    """Return a trimmed, lower-case question or raise ValueError."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    return question.strip().casefold()


def identify_intent(question):
    """Classify the broad shape of a question."""
    normalised = normalise_question(question)

    if normalised.startswith(("which ", "what ")):
        return "find_subjects"

    if normalised.startswith(("where ", "who ", "when ")):
        return "find_object"

    return "find_related_facts"


def identify_relationship(question):
    """Map common question wording to a relationship used by the knowledge base."""
    normalised = normalise_question(question)

    if re.search(r"\b(province|provinces|belong to|part of)\b", normalised):
        return "province"

    if re.search(r"\b(live|lives|living|reside|resides)\b", normalised):
        return "lives in"

    return None


def extract_search_term(question):
    """Return a simple readable search phrase for diagnostics and compatibility."""
    normalised = normalise_question(question)
    normalised = re.sub(r"^(which|what|where|who|when|tell me about)\s+", "", normalised)
    return normalised.rstrip("? .")


def analyse_question(question):
    """Analyse a question and return the information needed for retrieval."""
    normalised = normalise_question(question)

    return {
        "original_question": question,
        "normalised_question": normalised,
        "intent": identify_intent(normalised),
        "search_term": extract_search_term(normalised),
        "relationship": identify_relationship(normalised),
    }
