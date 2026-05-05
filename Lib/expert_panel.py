"""expert_panel.py — экосистема экспертов или ролей

Назначение:
- Собрать релевантные роли для запроса.
- Последовательно запустить каждого эксперта.
- Собрать вклады в единый bundle.
- Выполнить первичный синтез без LLM (чисто кодом).

По умолчанию выполняется последовательно. Опциональный режим THREADS запускает
только независимые expert calls параллельно и возвращает результат в порядке ролей.
"""

from __future__ import annotations

from Lib.expert_agent import run_expert
from Lib.expert_roles import BASE_EXPERT_ROLES, ExpertRole
from Lib.expert_selector import determine_expert_roles
from Lib.parallel_utils import normalize_max_workers, normalize_parallel_mode, run_ordered_thread_tasks


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
    dynamic_roles: list[ExpertRole] | None = None,
    execution_mode: str = "SEQUENTIAL",
    max_workers: int | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Запускает экспертную панель и возвращает роли, вклады и синтез.

    Структура результата:
    - roles: компактные метаданные ролей
    - contributions: индивидуальные вклады экспертов
    - synthesis: объединённые recommendations/risks/questions + counts по перспективам
    """
    roles = determine_expert_roles(query, max_roles=max_roles, context=context, dynamic_roles=dynamic_roles)
    dynamic_role_views = {}
    if isinstance(context, dict) and isinstance(context.get("dynamic_role_views"), list):
        for view in context.get("dynamic_role_views", []):
            if isinstance(view, dict) and isinstance(view.get("key"), str):
                dynamic_role_views[view["key"]] = view
    dynamic_role_keys = {role.key for role in dynamic_roles or []}
    base_role_keys = {role.key for role in BASE_EXPERT_ROLES}

    contributions: list[dict] = []

    all_recommendations_raw: list[str] = []
    all_risks_raw: list[str] = []
    all_questions_raw: list[str] = []
    perspective_counts: dict[str, int] = {}

    def run_one(role: ExpertRole) -> dict:
        try:
            contribution = run_expert(role=role, query=query, context=context, model=model)
            if not isinstance(contribution, dict):
                raise ValueError("invalid contribution format")
            return contribution
        except Exception:
            return {
                "role_key": role.key,
                "perspective_tag": role.perspective_tag,
                "insights": [],
                "risks": ["expert_execution_failed"],
                "questions": [],
                "recommendations": [],
                "confidence": 0.0,
            }

    mode = normalize_parallel_mode(execution_mode)
    if mode == "THREADS" and len(roles) > 1:
        records = run_ordered_thread_tasks(
            roles,
            run_one,
            max_workers=normalize_max_workers(max_workers, len(roles)),
        )
        role_contributions = [
            record["result"] if record.get("ok") and isinstance(record.get("result"), dict) else run_one(role)
            for role, record in zip(roles, records)
        ]
    else:
        role_contributions = [run_one(role) for role in roles]

    for role, contribution in zip(roles, role_contributions):
        perspective_counts[role.perspective_tag] = perspective_counts.get(role.perspective_tag, 0) + 1
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

    role_views = []
    for role in roles:
        source_view = dynamic_role_views.get(role.key, {})
        is_dynamic = role.key in dynamic_role_keys or role.key not in base_role_keys
        view = {
            "key": role.key,
            "name": role.name,
            "perspective_tag": role.perspective_tag,
        }
        if is_dynamic:
            view["dynamic"] = True
            if isinstance(source_view.get("why_needed"), str):
                view["why_needed"] = source_view.get("why_needed", "")
        else:
            view["dynamic"] = False
        role_views.append(view)

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
