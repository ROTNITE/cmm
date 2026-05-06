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

from Lib.expert_roles import ExpertRole
from Lib.json_retry import call_json_model
from Lib.json_utils import safe_json_loads
from Lib.state_fallbacks import build_rules_expert_contribution


def _fallback_output(
    role: ExpertRole,
    *,
    context: dict | None = None,
    query: str = "",
    warnings: list[str] | None = None,
    attempts: int = 0,
    raw: str = "",
) -> dict:
    """Фолбэк на случай ошибок модели/парсинга.

    IMPORTANT: Do NOT put technical errors like "invalid_json_from_model" into risks.
    Technical failures belong in parse_warnings, not expert_risks.
    The contribution is deterministic and role-aware so downstream stages keep
    useful evidence even when provider/API/JSON calls fail.
    """
    contribution = build_rules_expert_contribution(
        role,
        query,
        context=context,
        warnings=list(warnings or []) + ["expert_json_parse_failed"],
        raw=raw,
    )
    contribution["json_attempts"] = int(attempts or 0)
    return contribution


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
    """Приводит ответ модели к жёсткому контракту run_expert.

    Enforces exact counts: insights=3, risks=2, questions=2, recommendations=3.
    Truncates each string to 200 chars max.
    """
    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.0

    if confidence < 0.0:
        confidence = 0.0
    elif confidence > 1.0:
        confidence = 1.0

    def truncate_items(items: list[str], max_items: int, max_chars: int = 200) -> list[str]:
        result = []
        for item in items[:max_items]:
            if isinstance(item, str):
                truncated = item.strip()[:max_chars]
                if truncated:
                    result.append(truncated)
        return result

    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "insights": truncate_items(_to_string_list(payload.get("insights"), max_items=3), 3),
        "risks": truncate_items(_to_string_list(payload.get("risks"), max_items=2), 2),
        "questions": truncate_items(_to_string_list(payload.get("questions"), max_items=2), 2),
        "recommendations": truncate_items(_to_string_list(payload.get("recommendations"), max_items=3), 3),
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
        "\n"
        "You are providing expert input, not a final answer to the user.\n"
        "\n"
        "Quality standards for your contribution:\n"
        "- SPECIFIC: provide concrete, actionable insights, not generic statements\n"
        "- EVIDENCE-BASED: ground your insights in facts, examples, or clear reasoning\n"
        "- RISK-AWARE: identify real, specific risks with clear implications\n"
        "- ACTIONABLE: recommendations should be clear and implementable\n"
        "- PERSPECTIVE-DRIVEN: bring your unique expert viewpoint\n"
        "\n"
        "For insights: provide concrete observations or analysis from your perspective\n"
        "For risks: identify specific potential problems and their implications\n"
        "For questions: ask clarifying questions that would improve the answer\n"
        "For recommendations: suggest specific, actionable next steps\n"
        "\n"
        "CRITICAL: Return ONLY valid JSON. No markdown. No comments. No extra text.\n"
        "CRITICAL: Each item should be 1-2 sentences (max 200 chars per item).\n"
        "CRITICAL: Use EXACT counts below. Do not add more items.\n"
        "\n"
        "Schema:\n"
        "{\n"
        "  \"insights\": [\"string\", \"string\", \"string\"],\n"
        "  \"risks\": [\"string\", \"string\"],\n"
        "  \"questions\": [\"string\", \"string\"],\n"
        "  \"recommendations\": [\"string\", \"string\", \"string\"],\n"
        "  \"confidence\": 0.8\n"
        "}\n"
        "\n"
        "EXACT counts: insights=3, risks=2, questions=2, recommendations=3.\n"
        "Each item: 1-2 sentences, max 200 chars, specific and actionable."
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
        "Provide your expert contribution in JSON format following the schema.\n"
        "STRICT: insights=3, risks=2, questions=2, recommendations=3.\n"
        "Each item: 1-2 sentences (max 200 chars), specific and actionable.\n"
        "Return ONLY valid JSON object, no markdown blocks."
    )

    result = call_json_model(
        user_prompt="\n\n".join(user_prompt_parts),
        system_prompt=system_prompt,
        temp=0.2,
        tokens=800,
        model=model,
        max_retries=1,
    )

    parsed = result.get("payload") if isinstance(result, dict) else None
    warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    if not parsed:
        return _fallback_output(role, context=context, query=query, warnings=warnings, attempts=attempts, raw=raw)

    normalized = _normalize_output(role, parsed)
    normalized["parse_warnings"] = warnings
    normalized["json_attempts"] = attempts
    normalized["raw"] = raw[:2000]
    normalized["source"] = "model"
    return normalized
