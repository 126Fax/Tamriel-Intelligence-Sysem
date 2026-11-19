"""Run the interactive Top-Down AI from the repository root.

Start with: python -m top_down.chat
"""
from top_down.assistant import answer_question


def main():
    print("Tamriel Intelligence System — Top-Down AI")
    print("Ask about lore, request a count, or ask what the system knows.")
    print("Examples: 'What do you know about Skyrim?', 'How many provinces are there?'")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if question.casefold() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not question:
            continue
        try:
            result = answer_question(question)
        except (OSError, ValueError) as error:
            print(f"Knowledge retrieval error: {error}")
            continue
        print(f"AI: {result['answer']}")
        if result["facts"]:
            print("Evidence records:")
            for fact in result["facts"][:10]:
                print(f"  - {fact.get('subject', '?')} --[{fact.get('relationship', '?')}]--> {fact.get('object', '?')}")
        print()


if __name__ == "__main__":
    main()
