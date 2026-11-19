from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "knowledge_base.json"


def normalise_question(question):
    """Clean up a question before analysing it."""
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    return question.strip().casefold()


def identify_intent(question):
    """Identify what type of information a question requests."""
    question = normalise_question(question)

    # Import here to keep ordinary question analysis lightweight.
    from top_down.knowledge_overview import is_knowledge_overview_question

    if is_knowledge_overview_question(question):
        return "knowledge_overview"

    if question.startswith(("which ", "what ")):
        return "find_subjects"

    if question.startswith(("where ", "who ", "when ")):
        return "find_object"

    return "unknown"


def extract_search_term(question):
    """Extract the main subject or topic from a question."""
    question = normalise_question(question)
    question_starters = ["which ", "what ", "where ", "who ", "when "]

    for starter in question_starters:
        if question.startswith(starter):
            question = question[len(starter):]
            break

    return question.rstrip("? .")


def identify_relationship(question):
    """Identify the relationship requested in a question."""
    question = normalise_question(question)

    if "belong to" in question:
        return "province"
    if "live" in question or "lives" in question:
        return "lives in"
    return None


def analyse_question(question):
    """Analyse a question and return its recognised information."""
    return {
        "original_question": question,
        "normalised_question": normalise_question(question),
        "intent": identify_intent(question),
        "search_term": extract_search_term(question),
        "relationship": identify_relationship(question),
    }


def answer_question(question):
    """Handle supported direct-answer intents; return None if not handled."""
    if identify_intent(question) == "knowledge_overview":
        from top_down.knowledge_overview import answer_knowledge_overview
        return answer_knowledge_overview(question)
    return None


if __name__ == "__main__":
    questions = [
        "Which provinces belong to the Empire?",
        "Where do dragons live?",
        "WHO RULES SKYRIM?",
        "What do you know?",
    ]

    for question in questions:
        print("\n===== QUESTION ANALYSIS =====")
        result = analyse_question(question)
        for key, value in result.items():
            print(f"{key}: {value}")

        answer = answer_question(question)
        if answer is not None:
            print("\n===== ANSWER =====")
            print(answer)
