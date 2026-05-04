"""expert_agent.py — Запуск одного эксперта и получение его вклада.

Что делает этьот файл у нас:
- Принимает роль ExpertRole + пользовательский запрос (+ optional context).
- Формирует role-aware промпт.
- Возвращает структурированный вклад эксперта (JSON -> dict).

Важно:
- Эксперт даёт не финальный ответ, а аналитический вклад:
  insights / risks / questions / recommendations.
- На невалидном ответе модели модуль не падает, а возвращает fallback.
"""

from __future__ import annotations

import json
from typing import Any

from Lib.AI_request import send_to_AI
from Lib.expert_roles import ExpertRole
from Lib.json_utils import safe_json_loads


def _fallback_output(role: ExpertRole) -> dict:
    """Фолбэк на случай ошибок модели/парсинга."""
    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "insights": [],
        "risks": ["invalid_json_from_model"],
        "questions": [],
        "recommendations": [],
        "confidence": 0.0,
    }


def _safe_json_loads(raw: str) -> dict | None:
    """Безопасный парсинг JSON-объекта из текста модели."""
    return safe_json_loads(raw)


def _to_string_list(value: Any, max_items: int) -> list[str]:
    """Нормализует произвольный список в список непустых строк с лимитом."""
    if not isinstance(value, list):
        return []

    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
        if len(out) >= max_items:
            break

    return out


def _normalize_output(role: ExpertRole, payload: dict) -> dict:
    """Приводит ответ модели к жёсткому контракту run_expert."""
    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.0

    if confidence < 0.0:
        confidence = 0.0
    elif confidence > 1.0:
        confidence = 1.0

    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "insights": _to_string_list(payload.get("insights"), max_items=7),
        "risks": _to_string_list(payload.get("risks"), max_items=6),
        "questions": _to_string_list(payload.get("questions"), max_items=6),
        "recommendations": _to_string_list(payload.get("recommendations"), max_items=7),
        "confidence": confidence,
    }


def run_expert(
    role: ExpertRole,
    query: str,
    context: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Запускает одного эксперта и возвращает его структурированный вклад.

    Возврат всегда имеет фиксированный набор полей и не бросает исключения
    наружу из-за плохого JSON-ответа модели.
    """
    system_prompt = (
        f"{role.system_prompt}\n\n"
        "Original query is authoritative. Cleaned/formalized query is helper text only. "
        "Do not ignore constraints from original_query.\n"
        "Ты формируешь экспертный вклад, а не финальный ответ пользователю.\n"
        "Верни только JSON, без markdown, без комментариев, без лишнего текста.\n"
        "Строго соблюдай схему:\n"
        "{\n"
        "  \"insights\": [string,...],\n"
        "  \"risks\": [string,...],\n"
        "  \"questions\": [string,...],\n"
        "  \"recommendations\": [string,...],\n"
        "  \"confidence\": 0.0-1.0\n"
        "}"
    )

    context_text = ""
    if context:
        try:
            context_text = json.dumps(context, ensure_ascii=False)
        except Exception:
            context_text = "{}"

    user_prompt_parts = [
        f"Роль: {role.name} ({role.key})",
        f"Зона ответственности: {role.responsibility}",
        f"Запрос пользователя:\n{query}",
    ]

    if context_text:
        user_prompt_parts.append(f"Контекст:\n{context_text}")

    user_prompt_parts.append(
        "Сформируй экспертный вклад в JSON по схеме. "
        "Количество элементов: insights 3-7, risks 2-6, questions 2-6, recommendations 3-7."
    )

    raw = send_to_AI(
        user_prompt="\n\n".join(user_prompt_parts),
        system_prompt=system_prompt,
        temp=0.25,
        tokens=220,
        model=model,
    )

    parsed = _safe_json_loads(raw if isinstance(raw, str) else "")
    if not parsed:
        return _fallback_output(role)

    return _normalize_output(role, parsed)
