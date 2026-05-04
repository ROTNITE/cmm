# agent_improver.py - улучшатор. Может также переработать черновик по фидбеку.

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

# Импорт функции запроса к LLM (поддержка двух вариантов структуры проекта)
try:
    from Lib.AI_request import send_to_AI
    from Lib.deliberation import build_deliberation_brief
except Exception:
    from AI_request import send_to_AI
    from deliberation import build_deliberation_brief


def _plan_to_text(plan: Dict[str, Any],
                  max_steps: int = 12,
                  max_substeps: int = 6) -> str:
    """Делает компактное текстовое представление плана для промпта."""
    if not isinstance(plan, dict):
        return "ПЛАН: (ошибка формата — ожидался dict)"

    parts: List[str] = []
    parts.append(f"ОСНОВНАЯ ИДЕЯ: {plan.get('main_idea', '')}".strip())

    prep = plan.get("preparation", [])
    if prep:
        parts.append("ПОДГОТОВКА:")
        for x in prep[:10]:
            parts.append(f"- {x}")

    parts.append("ШАГИ:")
    steps = plan.get("steps", [])
    for i, step in enumerate(steps[:max_steps], start=1):
        if not isinstance(step, dict):
            continue
        title = step.get("title", f"Шаг {i}")
        parts.append(f"{i}. {title}")
        for sub in (step.get("substeps", []) or [])[:max_substeps]:
            parts.append(f"   - {sub}")

    nuances = plan.get("nuances", [])
    if nuances:
        parts.append("НЮАНСЫ:")
        for n in nuances[:10]:
            parts.append(f"- {n}")

    problems = plan.get("potential_problems", [])
    if problems:
        parts.append("ПОТЕНЦИАЛЬНЫЕ ПРОБЛЕМЫ:")
        for p in problems[:10]:
            parts.append(f"- {p}")

    res = plan.get("result", "")
    if res:
        parts.append(f"РЕЗУЛЬТАТ: {res}")

    return "\n".join([p for p in parts if p.strip()])


def _brief_to_text(deliberation_brief: Optional[Dict[str, Any]]) -> str:
    """Compact expert deliberation context for the answer prompt."""
    if not isinstance(deliberation_brief, dict):
        return ""

    parts: List[str] = []

    def add_list(title: str, key: str, max_items: int) -> None:
        values = deliberation_brief.get(key, [])
        if not isinstance(values, list):
            return
        cleaned = [str(x).strip() for x in values if str(x).strip()][:max_items]
        if not cleaned:
            return
        parts.append(title)
        for item in cleaned:
            parts.append(f"- {item}")

    add_list("ЭКСПЕРТНЫЕ РЕКОМЕНДАЦИИ:", "expert_recommendations", 8)
    add_list("ЭКСПЕРТНЫЕ РИСКИ:", "expert_risks", 8)
    add_list("ВОПРОСЫ, КОТОРЫЕ СТОИТ УЧЕСТЬ:", "expert_questions", 5)
    add_list("ОБЯЗАТЕЛЬНО УЧЕСТЬ:", "must_address", 10)
    add_list("ЗАМЕТКИ О БАЛАНСЕ ПЕРСПЕКТИВ:", "balance_notes", 5)
    add_list("ОГРАНИЧЕНИЯ ИЗ QUERY INTAKE:", "constraints", 8)
    add_list("КРИТЕРИИ УСПЕХА ИЗ QUERY INTAKE:", "success_criteria", 6)
    add_list("НЕИЗВЕСТНЫЕ ИЗ QUERY INTAKE:", "unknowns", 5)
    add_list("ПРЕДПОЧТЕНИЯ ПОЛЬЗОВАТЕЛЯ:", "user_preferences", 5)

    task_goal = deliberation_brief.get("task_goal")
    if isinstance(task_goal, str) and task_goal.strip():
        parts.append("ЦЕЛЬ ЗАПРОСА: " + task_goal.strip())

    for key, title in (("complexity", "СЛОЖНОСТЬ"), ("risk_level", "УРОВЕНЬ РИСКА")):
        value = deliberation_brief.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{title}: {value.strip()}")

    missing = deliberation_brief.get("missing_perspectives", [])
    if isinstance(missing, list) and missing:
        parts.append("НЕДОСТАЮЩИЕ ПЕРСПЕКТИВЫ: " + ", ".join(str(x) for x in missing[:8]))

    if deliberation_brief.get("dominant_perspective_found"):
        parts.append("ОБНАРУЖЕН ПЕРЕКОС ПЕРСПЕКТИВ: да")

    return "\n".join(parts)


def improve_plan_to_answer(
        original_query: str,
        plan: Dict[str, Any],
        critique: Optional[Dict[str, Any]] = None,
        expert_bundle: Optional[Dict[str, Any]] = None,
        balance_report: Optional[Dict[str, Any]] = None,
        deliberation_brief: Optional[Dict[str, Any]] = None,
        previous_answer: Optional[str] = None,
        feedback: Optional[List[str]] = None,
        depth: str = "standard",
        model: str = "deepseek-chat"
) -> Dict[str, Any]:
    """
    Возвращает:
      {
        "answer": str,
        "timestamp": str,
        "used_feedback": [...],
        "depth": "...",
      }
    """

    settings = {
        "quick": {"tokens": 450, "temp": 0.35},
        "standard": {"tokens": 850, "temp": 0.55},
        "thorough": {"tokens": 1100, "temp": 0.6},
    }
    cfg = settings.get(depth, settings["standard"])

    plan_text = _plan_to_text(plan)
    if deliberation_brief is None and (expert_bundle is not None or balance_report is not None):
        deliberation_brief = build_deliberation_brief(
            query=original_query,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
        )
    deliberation_text = _brief_to_text(deliberation_brief)

    critique_recs: List[str] = []
    if isinstance(critique, dict):
        critique_recs = (critique.get("recommendations") or [])[:8]

    extra_feedback: List[str] = []
    if feedback:
        extra_feedback = [str(x) for x in feedback][:10]

    system_prompt = (
        "Ты агент-улучшатор.\n"
        "Твоя задача — написать КОНЕЧНЫЙ ответ пользователю по запросу, "
        "опираясь на предоставленный план.\n\n"
        "Правила:\n"
        "0) Original query is authoritative. Cleaned/formalized query is helper text only. "
        "Do not ignore constraints from original_query.\n"
        "1) Не упоминай слова 'план', 'критик', 'агент', 'системный промпт'.\n"
        "2) Пиши в формате, удобном пользователю: краткое резюме → пошагово → нюансы/ошибки → итог.\n"
        "3) Если есть замечания/фидбек — обязательно исправь их.\n"
        "4) Если есть экспертный контекст, отрази важные риски и рекомендации в ответе.\n"
        "5) Не выдумывай конкретные факты/цифры, если они не требуются запросом. "
        "Если не уверен — формулируй как варианты.\n"
        "6) Верни только текст ответа (без служебных комментариев)."
    )

    user_prompt_parts = [
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{original_query}".strip(),
        f"\nПЛАН ДЕЙСТВИЙ (внутренний):\n{plan_text}".strip()
    ]

    if deliberation_text:
        user_prompt_parts.append(
            "\nЭКСПЕРТНЫЙ СИНТЕЗ И БАЛАНС (внутренний контекст):\n"
            f"{deliberation_text}".strip()
        )

    if previous_answer:
        user_prompt_parts.append(
            "\nПРЕДЫДУЩИЙ ЧЕРНОВИК ОТВЕТА (нужно улучшить):\n"
            f"{previous_answer}".strip()
        )

    if critique_recs:
        user_prompt_parts.append(
            "\nЗАМЕЧАНИЯ КРИТИКА (учти при улучшении):\n- " + "\n- ".join(critique_recs)
        )

    if extra_feedback:
        user_prompt_parts.append(
            "\nДОПОЛНИТЕЛЬНЫЙ ФИДБЕК ОТ МОДЕРАТОРА (обязательно исправь):\n- " + "\n- ".join(extra_feedback)
        )

    user_prompt_parts.append("\nСгенерируй улучшенный итоговый ответ.")

    response = send_to_AI(
        user_prompt="\n\n".join(user_prompt_parts),
        system_prompt=system_prompt,
        temp=cfg["temp"],
        tokens=cfg["tokens"],
        model=model
    )

    if not response or isinstance(response, Exception):
        response = "Не удалось сгенерировать ответ (ошибка модели). Попробуйте повторить запрос."

    return {
        "answer": response.strip(),
        "timestamp": str(datetime.now()),
        "used_feedback": extra_feedback,
        "depth": depth,
        "meta": {
            "agent": "improver",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "depth": depth,
            "temp": cfg["temp"],
            "tokens": cfg["tokens"],
            "feedback_count": len(extra_feedback),
            "critique_recommendations_count": len(critique_recs),
            "has_previous_answer": bool(previous_answer),
            "expert_bundle_used": isinstance(expert_bundle, dict),
            "balance_report_used": isinstance(balance_report, dict),
            "deliberation_brief_used": isinstance(deliberation_brief, dict),
        },
    }
