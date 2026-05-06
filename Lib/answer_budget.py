"""Deterministic answer-budget helpers for concise CMM outputs."""

from __future__ import annotations

import re
from typing import Any


_CONCISE_MARKERS = (
    "кратко",
    "коротко",
    "сжато",
    "лаконично",
    "briefly",
    "concise",
    "concisely",
    "short answer",
    "keep it short",
    "keep it concise",
)

_SIMPLE_LANGUAGE_MARKERS = (
    "простым языком",
    "простыми словами",
    "simple terms",
    "plain language",
    "for beginners",
)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(item or "") for item in value)
    if isinstance(value, dict):
        return " ".join(str(item or "") for item in value.values())
    return str(value or "")


def _combined_request_text(query: str, query_intake: dict | None = None) -> str:
    intake = query_intake if isinstance(query_intake, dict) else {}
    parts = [
        str(query or ""),
        _as_text(intake.get("constraints")),
        _as_text(intake.get("success_criteria")),
        _as_text(intake.get("user_preferences")),
    ]
    return "\n".join(part for part in parts if part)


def _sentence_limit(text: str) -> int | None:
    patterns = (
        r"(?:до|не более|максимум)\s+(\d{1,2})\s+(?:предложен|фраз)",
        r"(?:in|under|within|max(?:imum)?|no more than)\s+(\d{1,2})\s+sentences?",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            try:
                value = int(match.group(1))
            except Exception:
                continue
            if 1 <= value <= 12:
                return value
    return None


def derive_answer_budget(query: str, query_intake: dict | None = None, mode: str = "DIRECT") -> dict:
    """Infer a small deterministic answer budget from user-visible constraints.

    Uses adaptive logic:
    - Detects question type (comparison, definition, needs examples)
    - Adjusts char limits based on question type and CMM mode
    - More generous for questions requiring examples
    - Different budgets for DIRECT, LIGHT_CMM, FULL_CMM

    Args:
        query: Original user query
        query_intake: Query intake dict with constraints/preferences
        mode: CMM mode - "DIRECT", "LIGHT_CMM", or "FULL_CMM"
    """
    text = _combined_request_text(query, query_intake)
    lowered = text.lower()
    concise = any(marker in lowered for marker in _CONCISE_MARKERS)
    simple_language = any(marker in lowered for marker in _SIMPLE_LANGUAGE_MARKERS)
    sentence_limit = _sentence_limit(text)

    # Detect question type
    is_comparison = any(marker in lowered for marker in (
        'vs', 'versus', 'difference between', 'compare', 'разница между', 'сравн'
    ))
    is_definition = any(marker in lowered for marker in (
        'what is', 'define', 'explain', 'что такое', 'объясни', 'определение'
    ))
    has_example_request = any(marker in lowered for marker in (
        'example', 'пример', 'например', 'for instance'
    ))
    needs_examples = is_comparison or is_definition or has_example_request

    # Detect detailed request markers
    detailed_request = any(marker in lowered for marker in (
        'detailed', 'подробно', 'детально', 'comprehensive', 'полный'
    ))

    max_sentences = sentence_limit
    if concise and max_sentences is None:
        max_sentences = 5

    # Mode-specific char limits
    if mode == "DIRECT":
        # DIRECT mode: compact answers
        if needs_examples:
            max_chars = 1000 if concise else 2200
        else:
            max_chars = 650 if concise else 2200
    elif mode == "LIGHT_CMM":
        # LIGHT_CMM: 1200-2500 chars default
        if concise:
            max_chars = 1200
        elif detailed_request:
            max_chars = 2500
        else:
            max_chars = 2000
    elif mode == "FULL_CMM":
        # FULL_CMM: 2500-4500 chars, more only if user requests detailed document
        if concise:
            max_chars = 2500
        elif detailed_request:
            max_chars = 4500
        else:
            max_chars = 3500
    else:
        # Fallback to DIRECT logic
        max_chars = 1000 if concise else 2200

    if sentence_limit is not None:
        # For explicit sentence limits, give more chars per sentence
        max_chars = min(max_chars, max(400, sentence_limit * 200))

    return {
        "concise": bool(concise or sentence_limit is not None),
        "simple_language": bool(simple_language),
        "max_sentences": max_sentences,
        "max_chars": max_chars,
        "example_limit": 3 if concise or sentence_limit is not None else 5,
        "needs_examples": needs_examples,
        "question_type": "comparison" if is_comparison else "definition" if is_definition else "general",
        "mode": mode,
        "detailed_request": detailed_request,
    }


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def enforce_answer_budget(answer: str, budget: dict | None = None) -> str:
    """Trim obvious verbosity while preserving complete sentence boundaries.

    Adaptive enforcement:
    - Gives 30% buffer if answer has examples and they're needed
    - Preserves quality over strict length limits
    """
    text = re.sub(r"[ \t]+", " ", str(answer or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return ""

    budget = budget if isinstance(budget, dict) else {}
    max_sentences = budget.get("max_sentences")
    max_chars = budget.get("max_chars")
    needs_examples = budget.get("needs_examples", False)

    # Check if answer contains examples
    has_examples = bool(re.search(r'(example|пример|например|for instance|such as|e\.g\.|например)', text.lower()))

    # If examples are needed and present, give 30% buffer
    if needs_examples and has_examples and isinstance(max_chars, int) and len(text) < max_chars * 1.3:
        max_chars = int(max_chars * 1.3)

    if isinstance(max_sentences, int) and max_sentences > 0:
        sentences = _split_sentences(text)
        if len(sentences) > max_sentences:
            text = " ".join(sentences[:max_sentences]).strip()

    if isinstance(max_chars, int) and max_chars > 0 and len(text) > max_chars:
        sentences = _split_sentences(text)
        kept: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = (current + " " + sentence).strip() if current else sentence
            if len(candidate) > max_chars:
                break
            kept.append(sentence)
            current = candidate
        if kept:
            text = " ".join(kept).strip()
        if len(text) > max_chars:
            cut = text[:max_chars].rstrip()
            boundary = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            if boundary >= max(80, int(max_chars * 0.55)):
                text = cut[: boundary + 1].strip()
            else:
                text = cut.rstrip(" ,;:-") + "..."

    return text.strip()


__all__ = ["derive_answer_budget", "enforce_answer_budget"]
