"""Legacy/manual final polishing helper.

This module is outside the main CMM state-machine path. The active pipeline uses
``Lib.agent_moderator`` for answer moderation/revision. If this helper is used
manually, it must not add/remove substantive content or smooth away expert
risks; it should only polish wording.
"""

from Lib.AI_request import send_to_AI


def finish_answer(query: str, plan: dict, critique: dict = None, previous_answer: str = None,
                  model: str = "deepseek-chat") -> str:
    """
    Legacy polishing helper for manual use outside the main CMM state machine.
    """
    critique_recommendations = critique.get("recommendations", []) if isinstance(critique, dict) else []

    system_prompt = (
        "You are the final polishing agent. Your task is to take the finalized response "
        "and refine it to make it more readable, clear, and pleasant to the user. "
        "Do not add or remove substantive information. Do not hide, soften, or remove "
        "expert risks, constraints, trade-offs, or unresolved questions. Only improve "
        "phrasing, structure, and clarity."
    )

    user_prompt = (
        f"User query: {query}\n"
        f"Plan: {plan}\n"
        f"Critique recommendations: {critique_recommendations}\n"
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

    return refined_answer.strip() if isinstance(refined_answer, str) and refined_answer.strip() else "Unable to refine the response."
