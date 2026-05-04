"""Shared helpers for parsing untrusted JSON-like model output."""

from __future__ import annotations

import json
import re
from typing import Any


def safe_json_loads(raw: Any) -> dict | None:
    """Parse a JSON object from raw text, including markdown-wrapped JSON."""
    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    candidates = [text]

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if object_match:
        candidates.append(object_match.group(0).strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data

    return None


def to_string_list(value: Any, max_items: int) -> list[str]:
    """Normalize arbitrary list-like model output to non-empty strings."""
    if not isinstance(value, list):
        return []

    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, (int, float, bool)):
            text = str(item)
        else:
            continue
        if text:
            out.append(text)
        if len(out) >= max_items:
            break

    return out


def to_number(value: Any, default: float = 0.0, min_value: float = 0.0, max_value: float = 10.0) -> float:
    """Normalize numeric model output to a bounded float."""
    try:
        number = float(value)
    except Exception:
        return default

    if number < min_value:
        return min_value
    if number > max_value:
        return max_value
    return number
