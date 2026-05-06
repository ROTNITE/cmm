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


def derive_answer_budget(query: str, query_intake: dict | None = None) -> dict:
    """Infer a small deterministic answer budget from user-visible constraints."""
    text = _combined_request_text(query, query_intake)
    lowered = text.lower()
    concise = any(marker in lowered for marker in _CONCISE_MARKERS)
    simple_language = any(marker in lowered for marker in _SIMPLE_LANGUAGE_MARKERS)
    sentence_limit = _sentence_limit(text)

    max_sentences = sentence_limit
    if concise and max_sentences is None:
        max_sentences = 5
    max_chars = 650 if concise else 2200
    if sentence_limit is not None:
        max_chars = min(max_chars, max(260, sentence_limit * 180))

    return {
        "concise": bool(concise or sentence_limit is not None),
        "simple_language": bool(simple_language),
        "max_sentences": max_sentences,
        "max_chars": max_chars,
        "example_limit": 3 if concise or sentence_limit is not None else 4,
    }


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def enforce_answer_budget(answer: str, budget: dict | None = None) -> str:
    """Trim obvious verbosity while preserving complete sentence boundaries."""
    text = re.sub(r"[ \t]+", " ", str(answer or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return ""

    budget = budget if isinstance(budget, dict) else {}
    max_sentences = budget.get("max_sentences")
    max_chars = budget.get("max_chars")

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
