# agent_improver.py - улучшатор. Может также переработать черновик по фидбеку.

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Импорт функции запроса к LLM (поддержка двух вариантов структуры проекта)
try:
    from Lib.AI_request_instrumented import send_to_AI
    from Lib.deliberation import build_deliberation_brief
except Exception:
    from AI_request_instrumented import send_to_AI
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


def _is_model_error(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("error:")


def _fallback_answer_from_plan(original_query: str, plan: Dict[str, Any]) -> str:
    if not isinstance(plan, dict):
        plan = {}
    parts: List[str] = [
        "Не удалось получить стабильный ответ от модели. Ниже — краткий fallback на основе уже построенного плана.",
        "",
        f"Запрос: {original_query}".strip(),
    ]
    main_idea = plan.get("main_idea")
    if isinstance(main_idea, str) and main_idea.strip():
        parts.append(f"Основная идея: {main_idea.strip()}")

    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    if steps:
        parts.append("Ключевые шаги:")
        for index, step in enumerate(steps[:8], start=1):
            if isinstance(step, dict):
                title = str(step.get("title") or "").strip()
            else:
                title = str(step).strip()
            if title:
                parts.append(f"{index}. {title}")

    risks = plan.get("potential_problems") if isinstance(plan.get("potential_problems"), list) else []
    if risks:
        parts.append("Риски и ограничения:")
        for risk in risks[:6]:
            text = str(risk).strip()
            if text:
                parts.append(f"- {text}")

    if len(parts) <= 3:
        parts.append("Коротко: нужно ответить на запрос с учётом исходного контекста, ограничений и рисков.")
    return "\n".join(parts).strip()


def _string_list(value: Any, max_items: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in value if isinstance(value, list) else []:
        text = str(item or "").strip()
        marker = text.lower()
        if not text or marker in seen:
            continue
        seen.add(marker)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _tradeoff_texts(deliberation_brief: Optional[Dict[str, Any]]) -> List[str]:
    items: List[str] = []
    if not isinstance(deliberation_brief, dict):
        return items
    for tradeoff in deliberation_brief.get("unresolved_tradeoffs", []) or []:
        if isinstance(tradeoff, dict):
            value = tradeoff.get("tradeoff") or tradeoff.get("why_it_matters")
        else:
            value = tradeoff
        text = str(value or "").strip()
        if text:
            items.append(text)
        if len(items) >= 6:
            break
    return _string_list(items, 6)


def _synthesis_packet(
    *,
    original_query: str,
    plan: Dict[str, Any],
    critique: Optional[Dict[str, Any]],
    balance_report: Optional[Dict[str, Any]],
    deliberation_brief: Optional[Dict[str, Any]],
    feedback: Optional[List[str]],
) -> Dict[str, Any]:
    brief = deliberation_brief if isinstance(deliberation_brief, dict) else {}
    critique = critique if isinstance(critique, dict) else {}
    balance = balance_report if isinstance(balance_report, dict) else {}

    main_recommendation = ""
    if isinstance(plan.get("main_idea"), str) and plan.get("main_idea", "").strip():
        main_recommendation = plan["main_idea"].strip()
    elif isinstance(plan.get("result"), str) and plan.get("result", "").strip():
        main_recommendation = plan["result"].strip()
    else:
        main_recommendation = original_query

    return {
        "original_query": original_query,
        "main_recommendation": main_recommendation,
        "plan_steps": [
            {
                "number": str(step.get("number") or ""),
                "title": str(step.get("title") or "").strip(),
                "substeps": _string_list(step.get("substeps"), 5),
                "covers_constraints": _string_list(step.get("covers_constraints"), 5),
                "covers_success_criteria": _string_list(step.get("covers_success_criteria"), 5),
                "mitigates_risks": _string_list(step.get("mitigates_risks"), 5),
                "handles_tradeoffs": _string_list(step.get("handles_tradeoffs"), 5),
                "serves_stakeholders": _string_list(step.get("serves_stakeholders"), 5),
            }
            for step in (plan.get("steps") or [])[:8]
            if isinstance(step, dict)
        ],
        "constraints": _string_list(brief.get("constraints"), 8),
        "success_criteria": _string_list(brief.get("success_criteria"), 8),
        "expert_recommendations": _string_list(brief.get("expert_recommendations"), 10),
        "must_address": _string_list(brief.get("must_address"), 12),
        "risks": _string_list(brief.get("expert_risks"), 10),
        "tradeoffs": _tradeoff_texts(brief),
        "balance_blind_spots": _string_list(brief.get("balance_blind_spots") or balance.get("blind_spots"), 8),
        "moderation_feedback": _string_list(feedback, 10),
        "plan_critique_feedback": _string_list(critique.get("recommendations") or critique.get("feedback"), 10),
        "ignored_risks": _string_list(critique.get("ignored_risks") or critique.get("ignored_expert_risks"), 8),
        "ignored_tradeoffs": _string_list(critique.get("ignored_tradeoffs") or critique.get("unresolved_tradeoffs"), 8),
        "ignored_must_address": _string_list(critique.get("ignored_must_address"), 8),
    }


def _fallback_answer_from_context(
    *,
    original_query: str,
    plan: Dict[str, Any],
    critique: Optional[Dict[str, Any]],
    deliberation_brief: Optional[Dict[str, Any]],
) -> str:
    packet = _synthesis_packet(
        original_query=original_query,
        plan=plan,
        critique=critique,
        balance_report=None,
        deliberation_brief=deliberation_brief,
        feedback=[],
    )
    lines: List[str] = [
        "Не удалось получить стабильный ответ от модели. Ниже — fallback / best-effort ответ на основе собранного контекста.",
        "",
        f"Короткий вывод: {packet['main_recommendation']}",
    ]
    if packet["expert_recommendations"]:
        lines.append("")
        lines.append("Рекомендуемый подход:")
        for item in packet["expert_recommendations"][:4]:
            lines.append(f"- {item}")
    if packet["constraints"]:
        lines.append("")
        lines.append("Как учтены ограничения:")
        for item in packet["constraints"][:4]:
            lines.append(f"- {item}")
    if packet["must_address"]:
        lines.append("")
        lines.append("Что обязательно учесть:")
        for item in packet["must_address"][:4]:
            lines.append(f"- {item}")
    if packet["risks"]:
        lines.append("")
        lines.append("Ключевые риски:")
        for item in packet["risks"][:4]:
            lines.append(f"- {item}")
    if packet["tradeoffs"]:
        lines.append("")
        lines.append("Trade-offs:")
        for item in packet["tradeoffs"][:3]:
            lines.append(f"- {item}")
    if packet["plan_steps"]:
        lines.append("")
        lines.append("Реалистичные следующие шаги:")
        for index, step in enumerate(packet["plan_steps"][:5], start=1):
            title = step.get("title", "")
            if title:
                lines.append(f"{index}. {title}")
    if packet["balance_blind_spots"]:
        lines.append("")
        lines.append("Что ещё проверить перед запуском:")
        for item in packet["balance_blind_spots"][:4]:
            lines.append(f"- {item}")
    caveats = packet["ignored_must_address"] + packet["ignored_risks"] + packet["ignored_tradeoffs"]
    caveats = _string_list(caveats, 6)
    if caveats:
        lines.append("")
        lines.append("Что ещё нужно проверить:")
        for item in caveats[:5]:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


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
    synthesis_packet = _synthesis_packet(
        original_query=original_query,
        plan=plan,
        critique=critique,
        balance_report=balance_report,
        deliberation_brief=deliberation_brief,
        feedback=feedback,
    )

    critique_recs: List[str] = []
    if isinstance(critique, dict):
        critique_recs = (critique.get("recommendations") or [])[:8]

    extra_feedback: List[str] = []
    if feedback:
        extra_feedback = [str(x) for x in feedback][:10]

    system_prompt = (
        "Ты агент-улучшатор.\n"
        "Твоя задача — написать КОНЕЧНЫЙ ответ пользователю по запросу, "
        "опираясь на structured synthesis packet и предоставленный план.\n\n"
        "Правила:\n"
        "0) Original query is authoritative. Cleaned/formalized query is helper text only. "
        "Do not ignore constraints from original_query.\n"
        "1) Не упоминай слова 'план', 'критик', 'агент', 'системный промпт'.\n"
        "2) Для сложных и best-effort кейсов пиши в стабильной структуре: "
        "краткий вывод -> рекомендуемый подход -> как учтены ограничения -> ключевые риски -> "
        "trade-offs -> реалистичные next steps -> что остается uncertain или needs validation.\n"
        "3) Если есть замечания/фидбек — обязательно исправь их.\n"
        "4) Если есть экспертный контекст, отрази важные риски и рекомендации в ответе.\n"
        "5) Если critique указывает ignored risks, ignored must-address или unresolved trade-offs, "
        "они должны быть либо закрыты в ответе, либо честно перечислены как caveats.\n"
        "6) Не выдумывай конкретные факты/цифры, если они не требуются запросом. "
        "Если не уверен — формулируй как варианты.\n"
        "7) Верни только текст ответа (без служебных комментариев).\n"
        "8) Structured synthesis packet приоритетнее общего outline плана: используй его как источник содержания, "
        "а план — как scaffold для порядка."
    )

    user_prompt_parts = [
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{original_query}".strip(),
        "\nSTRUCTURED SYNTHESIS PACKET (внутренний контекст):\n"
        + json.dumps(synthesis_packet, ensure_ascii=False, indent=2),
        f"\nПЛАН ДЕЙСТВИЙ (внутренний scaffold):\n{plan_text}".strip(),
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
        model=model,
        log_purpose="answer_generator",
    )

    source = "model"
    if not response or isinstance(response, Exception) or _is_model_error(response):
        response = _fallback_answer_from_context(
            original_query=original_query,
            plan=plan,
            critique=critique,
            deliberation_brief=deliberation_brief,
        )
        source = "fallback"

    return {
        "answer": response.strip(),
        "timestamp": str(datetime.now()),
        "used_feedback": extra_feedback,
        "depth": depth,
        "meta": {
            "agent": "improver",
            "source": source,
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
