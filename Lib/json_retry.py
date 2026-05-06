"""Small retry helper for JSON-first model calls."""

from __future__ import annotations

import re
from typing import Any, Callable

from Lib.AI_request import send_to_AI
from Lib.json_utils import safe_json_loads


def _is_model_error(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("error:")


def _strip_markdown_json(text: str) -> str:
    """Aggressively strip markdown code blocks from JSON output."""
    if not isinstance(text, str):
        return ""

    # Remove ```json ... ``` blocks
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text)
    text = re.sub(r'^```\s*', '', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    # Find first { and last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    return text


def call_json_model(
    *,
    user_prompt: str,
    system_prompt: str,
    model: str,
    temp: float,
    tokens: int,
    parser: Callable[[Any], dict | None] = safe_json_loads,
    max_retries: int = 1,
) -> dict:
    """Call a model for strict JSON and retry once with a repair prompt."""
    warnings: list[str] = []
    attempts = 0
    raw = ""
    max_attempts = max(1, int(max_retries) + 1)
    current_user_prompt = user_prompt
    current_system_prompt = system_prompt

    for attempt_index in range(1, max_attempts + 1):
        attempts = attempt_index
        try:
            response = send_to_AI(
                user_prompt=current_user_prompt,
                system_prompt=current_system_prompt,
                temp=temp,
                tokens=tokens,
                model=model,
            )
        except Exception as exc:
            raw = ""
            warnings.append(f"json_model_call_failed_attempt_{attempt_index}: {exc}")
            response = ""

        raw = response if isinstance(response, str) else ""
        if raw.strip() and not _is_model_error(raw):
            # Try aggressive markdown stripping
            cleaned = _strip_markdown_json(raw)
            payload = parser(cleaned)
            if isinstance(payload, dict):
                return {"payload": payload, "raw": raw, "attempts": attempts, "warnings": warnings}
            warnings.append(f"json_parse_failed_attempt_{attempt_index}")
        else:
            warnings.append(f"json_model_empty_or_error_attempt_{attempt_index}")

        if attempt_index < max_attempts:
            warnings.append("json_retry_after_invalid_json")
            current_system_prompt = (
                f"{system_prompt}\n\n"
                "CRITICAL: Your previous output was INVALID JSON.\n"
                "Return ONLY a valid JSON object. Start with { and end with }.\n"
                "Do NOT use markdown code blocks (```json).\n"
                "Do NOT add explanations before or after the JSON.\n"
                "Close ALL brackets and braces properly."
            )
            current_user_prompt = (
                "Your previous output was INVALID JSON and could not be parsed.\n\n"
                "CRITICAL REQUIREMENTS:\n"
                "1. Return ONLY valid JSON\n"
                "2. Start with { and end with }\n"
                "3. NO markdown blocks\n"
                "4. NO text before or after JSON\n"
                "5. Close all brackets properly\n\n"
                "Original request:\n"
                f"{user_prompt}\n\n"
                "Your previous invalid output (first 1000 chars):\n"
                f"{raw[:1000]}"
            )

    warnings.append("json_retry_exhausted")
    return {"payload": None, "raw": raw, "attempts": attempts, "warnings": warnings}
