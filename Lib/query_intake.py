"""Safe structured intake for user queries.

The original query is always the source of truth. The cleaned query and
model-extracted fields are helper context only.
"""

from __future__ import annotations

import json
import re
from typing import Any

from Lib.json_retry import call_json_model
from Lib.json_utils import to_string_list


_RISK_LEVELS = {"low", "medium", "high"}
_COMPLEXITY_LEVELS = {"simple", "moderate", "complex"}
_AUTHORITATIVE_RULE = (
    "Original query is authoritative. Cleaned/formalized query is helper text only. "
    "Do not ignore constraints from original_query."
)


def _mechanical_clean(text: str) -> str:
    """Normalize noisy text without changing meaning and without model calls."""
    if not text:
        return ""

    cleaned = str(text)
    quote_map = {
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "’": "'",
        "‘": "'",
        "`": "'",
    }
    for source, target in quote_map.items():
        cleaned = cleaned.replace(source, target)

    cleaned = re.sub(r"[–—−]", "-", cleaned)
    cleaned = re.sub(r"(.)\1{2,}", r"\1\1", cleaned)
    cleaned = re.sub(r"[!]{2,}", "!", cleaned)
    cleaned = re.sub(r"[?]{2,}", "?", cleaned)
    cleaned = re.sub(r"[.]{3,}", "...", cleaned)
    cleaned = re.sub(r"[,]{2,}", ",", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)

    def _dedupe_words(match: re.Match) -> str:
        word = match.group(1)
        return f"{word} {word}"

    cleaned = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", _dedupe_words, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|[;|]+", text)
    out: list[str] = []
    for part in parts:
        item = part.strip(" -\t\r\n")
        if item:
            out.append(item)
        if len(out) >= 12:
            break
    return out


def _items_by_markers(text: str, markers: tuple[str, ...], max_items: int) -> list[str]:
    items: list[str] = []
    for sentence in _split_sentences(text):
        lower = sentence.lower()
        # Skip metadata labels (eval format: "Контекст: X", "Ограничения: Y")
        if re.match(r'^\s*(контекст|ограничения|constraints?|context):\s*', lower):
            continue
        if any(marker in lower for marker in markers):
            items.append(sentence)
        if len(items) >= max_items:
            break
    return items


def _derive_complexity(original_query: str) -> str:
    text = original_query.lower()

    # For multi-line queries (eval format), analyze only the first line (actual question)
    # to avoid metadata content inflating complexity
    lines = text.split('\n')
    first_line = lines[0].strip()

    # If first line looks like a question/request, use it for analysis
    # Otherwise use full text (for single-line queries)
    if first_line and (
        first_line.endswith('?') or
        any(marker in first_line for marker in ('what', 'explain', 'define', 'что такое', 'объясни'))
    ):
        analysis_text = first_line
    else:
        # Remove metadata labels for full-text analysis
        analysis_text = re.sub(r'\b(контекст|ограничения|constraints?|context):\s*', '', text)

    words = analysis_text.split()

    complex_markers = (
        "стратег",
        "архитект",
        "междисцип",
        "multi",
        "stakeholder",
        "complex",
        "риски",
        "огранич",
        "критер",
        "план",
        "evaluation",
        "architecture",
    )
    if len(words) <= 12 and not any(marker in analysis_text for marker in complex_markers):
        return "simple"
    if len(words) > 80 or any(marker in analysis_text for marker in complex_markers):
        return "complex"
    return "moderate"


def _derive_risk_level(original_query: str) -> str:
    text = original_query.lower()
    if not text.strip():
        return "low"
    high_markers = (
        "medical",
        "medicine",
        "health",
        "legal",
        "law",
        "finance",
        "security",
        "safety",
        "медиц",
        "здоров",
        "право",
        "закон",
        "финанс",
        "безопас",
    )
    if any(marker in text for marker in high_markers):
        return "high"
    return "low"


def _truncate_task_goal(value: str, limit: int = 700) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _rule_based_intake(
    original_query: str,
    cleaned_query: str,
    warning: str | None = None,
    *,
    json_attempts: int = 0,
    extra_warnings: list[str] | None = None,
) -> dict:
    """Build conservative fallback/rules intake without model dependency."""
    source = "fallback" if warning else "rules"
    complexity = _derive_complexity(original_query)
    risk_level = _derive_risk_level(original_query)
    text_for_rules = cleaned_query or original_query

    constraints = _items_by_markers(
        text_for_rules,
        (
            "нельзя",
            "огранич",
            "долж",
            "важно",
            "без ",
            "бюджет",
            "срок",
            "constraint",
            "limited",
            "must",
            "cannot",
            "can't",
            "should",
            "need",
            "deadline",
            "budget",
        ),
        max_items=8,
    )
    success_criteria = _items_by_markers(
        text_for_rules,
        ("критер", "успех", "результ", "метрик", "оцен", "success", "metric", "result", "criteria"),
        max_items=6,
    )
    context = _items_by_markers(
        text_for_rules,
        ("контекст", "сейчас", "у нас", "проект", "команда", "current", "context", "project", "team"),
        max_items=6,
    )

    warnings = []
    if warning:
        warnings.append(warning)
    warnings.extend(extra_warnings or [])

    return {
        "original_query": original_query,
        "cleaned_query": cleaned_query or original_query,
        "task_goal": _truncate_task_goal(cleaned_query or original_query),
        "context": context,
        "constraints": constraints,
        "success_criteria": success_criteria,
        "unknowns": [],
        "user_preferences": [],
        "risk_level": risk_level,
        "complexity": complexity,
        "should_use_cmm": complexity in {"moderate", "complex"},
        "parse_warnings": warnings,
        "json_attempts": json_attempts,
        "source": source,
    }


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in allowed:
            return candidate
    return default


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"true", "yes", "1", "да"}:
            return True
        if candidate in {"false", "no", "0", "нет"}:
            return False
    return default


def _normalize_intake_payload(
    payload: dict | None,
    original_query: str,
    cleaned_query: str,
    *,
    parse_warnings: list[str] | None = None,
    json_attempts: int = 1,
) -> dict | None:
    if not isinstance(payload, dict):
        return None

    rules = _rule_based_intake(original_query, cleaned_query)
    task_goal = payload.get("task_goal")
    if not isinstance(task_goal, str) or not task_goal.strip():
        task_goal = rules["task_goal"]

    complexity = _normalize_enum(payload.get("complexity"), _COMPLEXITY_LEVELS, rules["complexity"])
    risk_level = _normalize_enum(payload.get("risk_level"), _RISK_LEVELS, rules["risk_level"])

    return {
        "original_query": original_query,
        "cleaned_query": cleaned_query or original_query,
        "task_goal": _truncate_task_goal(task_goal),
        "context": to_string_list(payload.get("context"), max_items=8),
        "constraints": to_string_list(payload.get("constraints"), max_items=10),
        "success_criteria": to_string_list(payload.get("success_criteria"), max_items=8),
        "unknowns": to_string_list(payload.get("unknowns"), max_items=8),
        "user_preferences": to_string_list(payload.get("user_preferences"), max_items=8),
        "risk_level": risk_level,
        "complexity": complexity,
        "should_use_cmm": _normalize_bool(payload.get("should_use_cmm"), complexity in {"moderate", "complex"}),
        "parse_warnings": parse_warnings or [],
        "json_attempts": json_attempts,
        "source": "model",
    }


def _model_intake(original_query: str, cleaned_query: str, *, model: str, max_ai_tokens: int) -> dict:
    system_prompt = (
        "You are a safe query intake extractor for a Collective Meta-Moderation pipeline.\n"
        f"{_AUTHORITATIVE_RULE}\n"
        "Do not rewrite the full query. Extract structure only. Do not remove constraints.\n"
        "\n"
        "Classification rules:\n"
        "- complexity=simple: definition/explanation requests (\"what is X\", \"explain Y\"), short queries (<15 words), no planning/strategy/architecture needed\n"
        "- complexity=moderate: planning, comparison, implementation questions with some constraints\n"
        "- complexity=complex: strategy, architecture, multi-stakeholder decisions, governance, high-stakes tradeoffs\n"
        "- risk_level=low: general knowledge, definitions, technical explanations (DEFAULT)\n"
        "- risk_level=medium: business decisions, moderate-stakes planning\n"
        "- risk_level=high: medical, legal, financial, security, safety domains ONLY\n"
        "- should_use_cmm=false: simple definitions/explanations with only formatting constraints (\"briefly\", \"in 5 sentences\")\n"
        "- should_use_cmm=true: planning, strategy, multi-perspective analysis needed\n"
        "\n"
        "Extraction rules:\n"
        "- constraints: ONLY extract explicitly stated constraints from the query. Do NOT extract words from the question itself (e.g., if query is \"Briefly explain X\", do NOT add \"Briefly\" as a constraint).\n"
        "- success_criteria: ONLY extract if explicitly stated. Do NOT infer or generate success criteria for simple definition/explanation questions.\n"
        "- context: ONLY extract if provided. Metadata labels like \"Context:\", \"Constraints:\" are NOT context content.\n"
        "\n"
        "IMPORTANT: Words like \"user\", \"пользователь\", \"team\", \"команда\" in context descriptions are NOT stakeholder markers unless the query asks to analyze their conflicting needs.\n"
        "\n"
        "Return strict JSON only, without markdown or commentary.\n"
        "Schema:\n"
        "{\n"
        '  "task_goal": "string",\n'
        '  "context": ["string"],\n'
        '  "constraints": ["string"],\n'
        '  "success_criteria": ["string"],\n'
        '  "unknowns": ["string"],\n'
        '  "user_preferences": ["string"],\n'
        '  "risk_level": "low|medium|high",\n'
        '  "complexity": "simple|moderate|complex",\n'
        '  "should_use_cmm": true|false\n'
        "}"
    )
    state = {
        "original_query": original_query,
        "cleaned_query_helper": cleaned_query,
        "instruction": _AUTHORITATIVE_RULE,
    }
    return call_json_model(
        user_prompt="Extract safe query intake structure:\n" + json.dumps(state, ensure_ascii=False),
        system_prompt=system_prompt,
        temp=0.2,
        tokens=max_ai_tokens,
        model=model,
        max_retries=1,
    )


def build_query_intake(
    original_query: str,
    *,
    model: str = "deepseek-chat",
    max_ai_tokens: int = 650,
) -> dict:
    """Return safe structured query intake with original_query preserved."""
    original = "" if original_query is None else str(original_query)
    cleaned = _mechanical_clean(original) or original

    if not original.strip():
        return _rule_based_intake(original, cleaned)

    try:
        result = _model_intake(original, cleaned, model=model, max_ai_tokens=max_ai_tokens)
        payload = result.get("payload") if isinstance(result, dict) else None
        retry_warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
        json_attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
        normalized = _normalize_intake_payload(
            payload,
            original,
            cleaned,
            parse_warnings=retry_warnings,
            json_attempts=json_attempts,
        )
        if normalized is not None:
            return normalized
        warning = "model_intake_failed" if any("json_model_call_failed" in item for item in retry_warnings) else "model_intake_invalid_json"
        return _rule_based_intake(
            original,
            cleaned,
            warning=warning,
            json_attempts=json_attempts,
            extra_warnings=retry_warnings,
        )
    except Exception as exc:
        return _rule_based_intake(original, cleaned, warning=f"model_intake_failed: {exc}")
