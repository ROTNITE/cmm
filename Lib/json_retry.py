"""Small retry helper for JSON-first model calls."""

from __future__ import annotations

from typing import Any, Callable

from Lib.AI_request import send_to_AI
from Lib.json_utils import safe_json_loads


def _is_model_error(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("error:")


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
            payload = parser(raw)
            if isinstance(payload, dict):
                return {"payload": payload, "raw": raw, "attempts": attempts, "warnings": warnings}
            warnings.append(f"json_parse_failed_attempt_{attempt_index}")
        else:
            warnings.append(f"json_model_empty_or_error_attempt_{attempt_index}")

        if attempt_index < max_attempts:
            warnings.append("json_retry_after_invalid_json")
            current_system_prompt = (
                f"{system_prompt}\n\n"
                "Your previous output was invalid JSON. Return only valid JSON matching the schema. "
                "No markdown. No prose."
            )
            current_user_prompt = (
                "Your previous output was invalid JSON.\n"
                "Return only valid JSON matching the schema.\n"
                "No markdown. No prose.\n\n"
                "Original request:\n"
                f"{user_prompt}\n\n"
                "Previous invalid output:\n"
                f"{raw[:4000]}"
            )

    warnings.append("json_retry_exhausted")
    return {"payload": None, "raw": raw, "attempts": attempts, "warnings": warnings}
