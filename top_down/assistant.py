"""Public interface for asking the prototype a question."""

from top_down.answer_generator import generate_answer
from top_down.knowledge_retriever import load_knowledge_base, retrieve_facts
from top_down.question_analyser import analyse_question


def answer_question(question, knowledge_base_path=None):
    """Analyse a question, retrieve matching facts and return answer plus evidence."""
    analysis = analyse_question(question)
    facts = (
        load_knowledge_base(knowledge_base_path)
        if knowledge_base_path is not None
        else load_knowledge_base()
    )
    matches = retrieve_facts(analysis, facts)
    answer = generate_answer(question, analysis, matches)
    return {
        "question": question,
        "answer": answer,
        "analysis": analysis,
        "facts": matches,
        "knowledge_base_records": len(facts),
    }
