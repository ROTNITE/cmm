"""expert_panel.py — экосистема экспертов или ролей

Назначение:
- Собрать релевантные роли для запроса.
- Последовательно запустить каждого эксперта.
- Собрать вклады в единый bundle.
- Выполнить первичный синтез без LLM (чисто кодом).

Почему последовательно:
- Проще отлаживать и стабильнее поведение.
- Ошибка одного эксперта не должна ломать весь pipeline.
"""

from __future__ import annotations

from Lib.expert_agent import run_expert
from Lib.expert_selector import determine_expert_roles


def _unique_keep_order(items: list[str]) -> list[str]:
    """Уникализация списка с сохранением порядка первого появления."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def run_expert_panel(
    query: str,
    context: dict | None = None,
    max_roles: int = 5,
) -> dict:
    """Запускает экспертную панель и возвращает роли, вклады и синтез.

    Структура результата:
    - roles: компактные метаданные ролей
    - contributions: индивидуальные вклады экспертов
    - synthesis: объединённые recommendations/risks/questions + counts по перспективам
    """
    roles = determine_expert_roles(query, max_roles=max_roles)

    contributions: list[dict] = []

    all_recommendations_raw: list[str] = []
    all_risks_raw: list[str] = []
    all_questions_raw: list[str] = []
    perspective_counts: dict[str, int] = {}

    for role in roles:
        perspective_counts[role.perspective_tag] = perspective_counts.get(role.perspective_tag, 0) + 1

        try:
            contribution = run_expert(role=role, query=query, context=context)
            if not isinstance(contribution, dict):
                raise ValueError("invalid contribution format")
        except Exception:
            contribution = {
                "role_key": role.key,
                "perspective_tag": role.perspective_tag,
                "insights": [],
                "risks": ["expert_execution_failed"],
                "questions": [],
                "recommendations": [],
                "confidence": 0.0,
            }

        contributions.append(contribution)

        recs = contribution.get("recommendations", [])
        risks = contribution.get("risks", [])
        questions = contribution.get("questions", [])

        if isinstance(recs, list):
            all_recommendations_raw.extend(recs)
        if isinstance(risks, list):
            all_risks_raw.extend(risks)
        if isinstance(questions, list):
            all_questions_raw.extend(questions)

    role_views = [
        {
            "key": role.key,
            "name": role.name,
            "perspective_tag": role.perspective_tag,
        }
        for role in roles
    ]

    synthesis = {
        "recommendations": _unique_keep_order(all_recommendations_raw),
        "risks": _unique_keep_order(all_risks_raw),
        "questions": _unique_keep_order(all_questions_raw),
        "perspective_counts": perspective_counts,
    }

    return {
        "roles": role_views,
        "contributions": contributions,
        "synthesis": synthesis,
    }
