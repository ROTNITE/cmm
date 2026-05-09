"""Small retry helper for JSON-first model calls."""

from __future__ import annotations

import re
from typing import Any, Callable

from Lib.AI_request_instrumented import send_to_AI
from Lib.config import get_default_model, get_json_strategy
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
    model: str | None,
    temp: float,
    tokens: int,
    parser: Callable[[Any], dict | None] = safe_json_loads,
    max_retries: int | None = None,
    log_purpose: str = "",
    json_profile: dict | None = None,
) -> dict:
    """Call a model for strict JSON and retry once with a repair prompt."""
    profile = get_json_strategy()
    if isinstance(json_profile, dict):
        profile.update({key: value for key, value in json_profile.items() if value is not None})
    warnings: list[str] = []
    attempts = 0
    raw = ""
    effective_retries = profile.get("max_retries") if max_retries is None else max_retries
    max_attempts = max(1, int(effective_retries) + 1)
    repair_prompt = str(
        profile.get("repair_prompt")
        or "Your previous output was invalid JSON. Return one valid JSON object only. No markdown. No prose."
    )
    retry_tokens_factor = float(profile.get("retry_tokens_factor") or 1.0)
    current_user_prompt = user_prompt
    current_system_prompt = system_prompt
    resolved_model = get_default_model(model)
    current_tokens = int(tokens)

    for attempt_index in range(1, max_attempts + 1):
        attempts = attempt_index
        try:
            response = send_to_AI(
                user_prompt=current_user_prompt,
                system_prompt=current_system_prompt,
                temp=temp,
                tokens=current_tokens,
                model=resolved_model,
                log_purpose=log_purpose,
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
            current_system_prompt = f"{system_prompt}\n\n{repair_prompt}"
            current_user_prompt = (
                "Your previous output could not be parsed as JSON.\n"
                "Return one valid JSON object only.\n\n"
                "Original request:\n"
                f"{user_prompt}\n\n"
                "Previous invalid output excerpt:\n"
                f"{raw[:1000]}"
            )
            current_tokens = max(120, int(tokens * retry_tokens_factor))

    warnings.append("json_retry_exhausted")
    return {"payload": None, "raw": raw, "attempts": attempts, "warnings": warnings}
