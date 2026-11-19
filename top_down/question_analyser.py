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
    try:
        from .knowledge_overview import is_knowledge_overview_question
    except ImportError:
        from knowledge_overview import is_knowledge_overview_question

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
        try:
            from .knowledge_overview import answer_knowledge_overview
        except ImportError:
            from knowledge_overview import answer_knowledge_overview
        return answer_knowledge_overview(question)
    return None


if __name__ == "__main__":
    print("Tamriel Intelligence System — Top-down AI")
    print('Ask "What do you know?" to see its current knowledge inventory.')
    print("Type 'exit' or 'quit' to stop.\\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\nGoodbye.")
            break

        if question.casefold() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not question:
            continue

        answer = answer_question(question)
        if answer is not None:
            print(f"\\nAI: {answer}\\n")
        else:
            result = analyse_question(question)
            print(f"AI: I recognised the intent as '{result['intent']}', ")
            print("but this question type is not connected to a response handler yet.\\n")
