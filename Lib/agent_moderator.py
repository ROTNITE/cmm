# Lib/agent_moderator.py - модератор/метафасилитатор. Делает многокритериальную оценку и при необходимости инициирует доработку.

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from Lib.agent_improver import improve_plan_to_answer
from Lib.deliberation import build_deliberation_brief
from Lib.json_retry import call_json_model
from Lib.json_utils import safe_json_loads, to_number, to_string_list
from Lib.quality_gates import normalize_moderated_result


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    return safe_json_loads(s)


def _moderation_prompt_schema() -> str:
    return (
        "Верни СТРОГО JSON без пояснений и без markdown.\n"
        "Схема:\n"
        "{\n"
        '  "decision": "ACCEPT|REVISE|REJECT",\n'
        '  "scores": {\n'
        '    "content_novelty": 0-10,\n'
        '    "content_groundedness": 0-10,\n'
        '    "content_applicability": 0-10,\n'
        '    "process_stimulates_thinking": 0-10,\n'
        '    "process_opens_directions": 0-10,\n'
        '    "process_supports_synthesis": 0-10,\n'
        '    "expert_input_coverage": 0-10,\n'
        '    "balance_issue_handling": 0-10\n'
        "  },\n"
        '  "balance": {\n'
        '    "dominant_perspective_found": true|false,\n'
        '    "missing_perspectives": [string,...]\n'
        "  },\n"
        '  "critical_issues": [string,...],\n'
        '  "improvements": [string,...],\n'
        '  "ignored_expert_risks": [string,...],\n'
        '  "ignored_expert_recommendations": [string,...],\n'
        '  "unresolved_questions": [string,...]\n'
        "}\n"
    )


def _normalize_moderation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    scores_raw = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    score_keys = [
        "content_novelty",
        "content_groundedness",
        "content_applicability",
        "process_stimulates_thinking",
        "process_opens_directions",
        "process_supports_synthesis",
        "expert_input_coverage",
        "balance_issue_handling",
    ]
    scores = {key: to_number(scores_raw.get(key), default=0.0) for key in score_keys}

    balance_raw = payload.get("balance") if isinstance(payload.get("balance"), dict) else {}
    balance = {
        "dominant_perspective_found": bool(balance_raw.get("dominant_perspective_found", False)),
        "missing_perspectives": to_string_list(balance_raw.get("missing_perspectives"), max_items=8),
    }

    decision = payload.get("decision", "REVISE")
    if not isinstance(decision, str) or decision not in {"ACCEPT", "REVISE", "REJECT"}:
        decision = "REVISE"

    unresolved_questions = to_string_list(payload.get("unresolved_questions"), max_items=10)
    if not unresolved_questions:
        unresolved_questions = to_string_list(payload.get("unresolved_balance_issues"), max_items=10)

    return {
        "decision": decision,
        "scores": scores,
        "balance": balance,
        "ignored_expert_risks": to_string_list(payload.get("ignored_expert_risks"), max_items=10),
        "ignored_expert_recommendations": to_string_list(
            payload.get("ignored_expert_recommendations"), max_items=10
        ),
        "unresolved_questions": unresolved_questions,
        "critical_issues": to_string_list(payload.get("critical_issues"), max_items=10),
        "improvements": to_string_list(payload.get("improvements"), max_items=10),
    }


def _brief_to_moderation_text(deliberation_brief: Optional[Dict[str, Any]]) -> str:
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
    add_list("ОБЯЗАТЕЛЬНО ДОЛЖНО БЫТЬ УЧТЕНО:", "must_address", 10)
    add_list("ЗАМЕТКИ О БАЛАНСЕ:", "balance_notes", 5)
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


def moderate_answer(
        original_query: str,
        plan: Dict[str, Any],
        answer: str,
        critique: Optional[Dict[str, Any]] = None,
        expert_bundle: Optional[Dict[str, Any]] = None,
        balance_report: Optional[Dict[str, Any]] = None,
        deliberation_brief: Optional[Dict[str, Any]] = None,
        min_avg_score: float = 7.5,
        model: str = "deepseek-chat"
) -> Dict[str, Any]:
    """
    Делает оценку ответа и возвращает решение + список улучшений.
    """

    critique_recs: List[str] = []
    if isinstance(critique, dict):
        critique_recs = (critique.get("recommendations") or [])[:8]

    if deliberation_brief is None and (expert_bundle is not None or balance_report is not None):
        deliberation_brief = build_deliberation_brief(
            query=original_query,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
        )
    deliberation_text = _brief_to_moderation_text(deliberation_brief)

    system_prompt = (
        "Ты модератор (метафасилитатор) коллективного обсуждения.\n"
        "Твоя задача — оценить качество ответа на запрос пользователя.\n"
        "Original query is authoritative. Cleaned/formalized query is helper text only. "
        "Do not ignore constraints from original_query.\n"
        "Оцени по содержательным и процессуальным критериям (как в книге), "
        "проверь баланс перспектив и сформируй точечные улучшения.\n"
        "Отдельно проверь, проигнорировал ли ответ важные экспертные риски, "
        "рекомендации или проблемы баланса.\n\n"
        + _moderation_prompt_schema()
    )

    user_prompt_parts = [
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{original_query}".strip(),
        f"\nОТВЕТ (который нужно оценить):\n{answer}".strip(),
    ]

    if critique_recs:
        user_prompt_parts.append(
            "\nРЕКОМЕНДАЦИИ КРИТИКА (если релевантно — учти при оценке):\n- " + "\n- ".join(critique_recs)
        )

    if deliberation_text:
        user_prompt_parts.append(
            "\nЭКСПЕРТНЫЙ СИНТЕЗ И БАЛАНС ДЛЯ ПРОВЕРКИ:\n"
            f"{deliberation_text}".strip()
        )

    user_prompt_parts.append(
        "\nТребования к решению:\n"
        "- ACCEPT: если ответ уже хорош и правки косметические.\n"
        "- REVISE: если нужно улучшить структуру/полноту/баланс/применимость.\n"
        "- REJECT: если ответ не по теме, опасно неверный или сильно неполный.\n"
        "- Если важный экспертный риск или рекомендация проигнорированы, перечисли это "
        "в ignored_expert_risks / ignored_expert_recommendations.\n"
        "- Если остались нерешенные экспертные вопросы, перекосы или отсутствующие перспективы, "
        "перечисли это в unresolved_questions.\n"
    )

    result = call_json_model(
        user_prompt="\n\n".join(user_prompt_parts),
        system_prompt=system_prompt,
        temp=0.25,
        tokens=650,
        model=model,
        max_retries=1,
    )

    parsed = result.get("payload") if isinstance(result, dict) else None
    retry_warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    if not parsed:
        # Фолбэк: если модель не вернула JSON — не ломаем пайплайн
        return {
            "decision": "REVISE",
            "scores": {},
            "balance": {"dominant_perspective_found": False, "missing_perspectives": []},
            "critical_issues": ["Moderator JSON output could not be parsed after retry."],
            "improvements": [
                "Regenerate answer with stricter structure and shorter sections.",
                "Ensure constraints, metrics, risks, and trade-offs are explicit.",
            ],
            "ignored_expert_risks": [],
            "ignored_expert_recommendations": [],
            "unresolved_questions": [],
            "parse_warnings": retry_warnings + ["moderation_json_parse_failed"],
            "json_attempts": attempts,
            "timestamp": str(datetime.now()),
            "raw": (raw or ""),
            "source": "fallback",
            "meta": {
                "expert_bundle_used": isinstance(expert_bundle, dict),
                "balance_report_used": isinstance(balance_report, dict),
                "deliberation_brief_used": isinstance(deliberation_brief, dict),
            },
        }

    parsed = _normalize_moderation_payload(parsed)

    # Авто-решение по среднему баллу (плюс критические проблемы)
    scores = parsed.get("scores", {}) or {}
    score_values = [v for v in scores.values() if isinstance(v, (int, float))]
    avg = (sum(score_values) / len(score_values)) if score_values else 0.0

    critical = parsed.get("critical_issues", []) or []
    ignored_risks = parsed.get("ignored_expert_risks", []) or []
    ignored_recs = parsed.get("ignored_expert_recommendations", []) or []
    unresolved_questions = parsed.get("unresolved_questions", []) or []
    decision = parsed.get("decision", "REVISE")

    if (critical or ignored_risks or ignored_recs or unresolved_questions) and decision == "ACCEPT":
        decision = "REVISE"
    if avg >= min_avg_score and not critical:
        decision = "ACCEPT"
    elif avg <= 4.0:
        decision = "REJECT"

    if (ignored_risks or ignored_recs or unresolved_questions) and decision == "ACCEPT":
        decision = "REVISE"

    parsed["decision"] = decision
    parsed["avg_score"] = avg
    parsed["timestamp"] = str(datetime.now())
    parsed["raw"] = (raw or "")
    parsed["parse_warnings"] = retry_warnings
    parsed["json_attempts"] = attempts
    parsed["source"] = "model"
    parsed["meta"] = {
        "expert_bundle_used": isinstance(expert_bundle, dict),
        "balance_report_used": isinstance(balance_report, dict),
        "deliberation_brief_used": isinstance(deliberation_brief, dict),
    }

    return parsed


def run_moderated_loop(
        original_query: str,
        plan: Dict[str, Any],
        critique: Optional[Dict[str, Any]] = None,
        expert_bundle: Optional[Dict[str, Any]] = None,
        balance_report: Optional[Dict[str, Any]] = None,
        deliberation_brief: Optional[Dict[str, Any]] = None,
        max_iters: int = 2,
        model: str = "deepseek-chat"
) -> Dict[str, Any]:
    """
    Full answer generation + moderation loop.

    Explicit Phase 6 contract:
    {
      "final_answer": str,
      "reports": [...],
      "final_decision": "ACCEPT|REVISE|REJECT",
      "critical_issues": [],
      "revision_count": int,
      "source": ...
    }
    """
    if deliberation_brief is None and (expert_bundle is not None or balance_report is not None):
        deliberation_brief = build_deliberation_brief(
            query=original_query,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
        )

    improver_out = improve_plan_to_answer(
        original_query=original_query,
        plan=plan,
        critique=critique,
        expert_bundle=expert_bundle,
        balance_report=balance_report,
        deliberation_brief=deliberation_brief,
        depth="standard",
        model=model,
    )
    answer = improver_out["answer"]

    reports: List[Dict[str, Any]] = []
    revision_count = 0

    for _ in range(max_iters + 1):
        report = moderate_answer(
            original_query=original_query,
            plan=plan,
            answer=answer,
            critique=critique,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            model=model,
        )
        reports.append(report)

        decision = str(report.get("decision") or "").upper()

        if decision == "ACCEPT":
            break

        if decision == "REJECT":
            break

        revision_count += 1

        feedback = (report.get("improvements") or [])[:10]
        improver_out = improve_plan_to_answer(
            original_query=original_query,
            plan=plan,
            critique=critique,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            previous_answer=answer,
            feedback=feedback,
            depth="thorough",
            model=model,
        )
        answer = improver_out["answer"]

    final_report = reports[-1] if reports else {}
    final_decision = str(final_report.get("decision") or "").upper()
    if final_decision not in {"ACCEPT", "REVISE", "REJECT"}:
        final_decision = "REVISE" if reports else "REJECT"

    critical_issues = final_report.get("critical_issues") if isinstance(final_report, dict) else []
    if not isinstance(critical_issues, list):
        critical_issues = []

    rejected = final_decision == "REJECT"

    result = {
        "final_answer": "" if rejected else answer,
        "rejected_answer": answer if rejected else "",
        "final_decision": final_decision,
        "rejected": bool(rejected),
        "critical_issues": critical_issues,
        "revision_count": revision_count,
        "source": final_report.get("source") if isinstance(final_report, dict) else "moderated_loop",
        "reports": reports,
        "trace": {
            "expert_bundle_used": isinstance(expert_bundle, dict),
            "balance_report_used": isinstance(balance_report, dict),
            "deliberation_brief": deliberation_brief,
        },
        "timestamp": str(datetime.now()),
    }

    return normalize_moderated_result(result)
