# Finish_agent.py

from Lib.AI_request import send_to_AI


def finish_answer(query: str, plan: dict, critique: dict = None, previous_answer: str = None,
                  model: str = "deepseek-chat") -> str:
    """
    This agent focuses on polishing the final response to the user after all previous analysis.
    It ensures the response is well-formatted, pleasant, and clear.
    """

    system_prompt = (
        "You are the final polishing agent. Your task is to take the finalized response "
        "and refine it to make it more readable, clear, and pleasant to the user. "
        "Do not add any new information, but enhance the phrasing, structure, and clarity."
    )

    user_prompt = (
        f"User query: {query}\n"
        f"Plan: {plan}\n"
        f"Critique recommendations: {critique.get('recommendations', [])}\n"
        f"Previous answer: {previous_answer}\n"
        "Refine and polish this content into a smooth and professional response."
    )

    refined_answer = send_to_AI(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=0.3,
        tokens=500,
        model=model
    )

    return refined_answer.strip() if refined_answer else "Unable to refine the response."