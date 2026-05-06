"""Instrumented AI request wrapper with token tracking for eval."""

from __future__ import annotations

from typing import Any

from Lib.AI_request import send_to_AI as _original_send_to_AI
from Lib.eval_logger import get_logger


def _estimate_tokens(text: str) -> int:
    """Rough token estimation: ~0.75 tokens per word for English/Russian."""
    if not text:
        return 0
    words = len(str(text).split())
    return int(words * 0.75)


def _infer_purpose_from_prompt(system_prompt: str, user_prompt: str) -> str:
    """Infer the purpose of the AI call from the prompts."""
    combined = (system_prompt + " " + user_prompt).lower()

    # Check for specific agent types
    if "router" in combined or "route query" in combined or "complexity" in combined:
        return "router"
    elif "expert" in combined and "contribution" in combined:
        return "expert_agent"
    elif "plan" in combined and ("develop" in combined or "steps" in combined):
        return "planner"
    elif "critique" in combined or "plan critic" in combined:
        return "plan_critic"
    elif "meta" in combined and "moderator" in combined:
        return "meta_moderator"
    elif "moderate" in combined and "answer" in combined:
        return "answer_moderator"
    elif "conflict" in combined or "analyze conflicts" in combined:
        return "conflict_analyzer"
    elif "balance" in combined or "analyze balance" in combined:
        return "balance_analyzer"
    elif "deliberation" in combined:
        return "deliberation"
    elif "query intake" in combined or "cleaned_query" in combined:
        return "query_intake"
    elif "direct answer" in combined:
        return "direct_answer"
    elif "judge" in combined or "evaluation" in combined:
        return "judge"
    elif "baseline" in combined:
        return "baseline"
    else:
        return "unknown"


def send_to_AI(
    user_prompt: str,
    system_prompt: str = "",
    history: list | None = None,
    temp: float = 0.65,
    top_p: float = 0.9,
    tokens: int | None = None,
    model: str = "deepseek-chat",
    stream: bool = False,
    api_key: str | None = None,
    log_purpose: str = "",
) -> str:
    """
    Instrumented version of send_to_AI that logs token usage.

    Args:
        log_purpose: Optional description of what this call is for (e.g., "router", "expert_agent", "judge")
    """
    logger = get_logger()

    # Infer purpose if not provided
    if not log_purpose:
        log_purpose = _infer_purpose_from_prompt(system_prompt, user_prompt)

    # Estimate input tokens
    prompt_text = f"{system_prompt}\n{user_prompt}"
    if history:
        for msg in history:
            if isinstance(msg, dict) and "content" in msg:
                prompt_text += f"\n{msg['content']}"

    estimated_prompt_tokens = _estimate_tokens(prompt_text)

    # Call original function
    response = _original_send_to_AI(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        history=history,
        temp=temp,
        top_p=top_p,
        tokens=tokens,
        model=model,
        stream=stream,
        api_key=api_key,
    )

    # Estimate completion tokens
    estimated_completion_tokens = _estimate_tokens(response)
    total_tokens = estimated_prompt_tokens + estimated_completion_tokens

    # Log the call
    logger.ai_call(
        model=model,
        prompt_tokens=estimated_prompt_tokens,
        completion_tokens=estimated_completion_tokens,
        total_tokens=total_tokens,
        purpose=log_purpose,
    )

    return response
