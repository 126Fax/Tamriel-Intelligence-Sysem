"""Command-line entry point for the Tamriel Top-Down AI."""

from top_down.answer_generator import generate_answer
from top_down.knowledge_retriever import load_knowledge_base, retrieve_facts
from top_down.question_analyser import analyse_question


def answer_question(question):
    """Run the complete question-analysis, retrieval and answer process."""
    analysis = analyse_question(question)
    facts = retrieve_facts(analysis)
    return generate_answer(question, facts)


def main():
    """Start an interactive lore question-and-answer session."""
    try:
        fact_count = len(load_knowledge_base())
    except (OSError, ValueError) as error:
        print(f"Could not load the knowledge base: {error}")
        return

    print("Tamriel Intelligence System — Top-Down AI")
    print(f"Knowledge base loaded: {fact_count} facts.")
    print("Ask a question, or type 'exit' to quit.\n")

    while True:
        try:
            question = input("You: ").strip()

            if question.casefold() in {"exit", "quit"}:
                print("Goodbye.")
                break

            if not question:
                continue

            print(f"AI: {answer_question(question)}\n")

        except ValueError as error:
            print(f"AI: {error}\n")


if __name__ == "__main__":
    main()
