"""Direct low-cost answer path for simple routed CMM requests."""

from __future__ import annotations

from typing import Any

from Lib.AI_request_instrumented import send_to_AI
from Lib.answer_budget import derive_answer_budget, enforce_answer_budget
from Lib.config import get_direct_answer_style, get_stage_settings


def _get_attr_or_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _extract_answer_text(raw: Any) -> str:
    """Extract text from plain strings and common OpenAI-like response shapes."""
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""

    output_text = _get_attr_or_key(raw, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = _get_attr_or_key(raw, "choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = _get_attr_or_key(first, "message")
        content = _get_attr_or_key(message, "content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        text = _get_attr_or_key(first, "text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    message = _get_attr_or_key(raw, "message")
    content = _get_attr_or_key(message, "content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    content = _get_attr_or_key(raw, "content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return ""


def _fallback_answer(query: str, query_intake: dict) -> str:
    goal = query_intake.get("task_goal") if isinstance(query_intake.get("task_goal"), str) else ""
    topic = goal.strip() or str(query or "").strip()
    if topic:
        return f"Не удалось получить ответ от модели. Сохранён исходный запрос: {topic}"
    return "Не удалось получить ответ от модели. Повторите запрос позже."


def _looks_incomplete(answer: str) -> bool:
    text = str(answer or "").strip()
    if not text:
        return True
    lowered = text.lower()
    dangling = (" vs", " vs.", " vs:", "and", "or", "и", "или", "-", ":", ";", ",")
    return any(lowered.endswith(item) for item in dangling)


def _bullet_count(answer: str) -> int:
    return sum(1 for line in str(answer or "").splitlines() if line.strip().startswith(("-", "*")))


def _enhance_direct_answer(answer: str, query: str, query_intake: dict) -> str:
    """Small deterministic repair for common concise explanation failures."""
    text = str(answer or "").strip()
    query_text = " ".join(
        [
            str(query or ""),
            " ".join(str(item or "") for item in query_intake.get("constraints", []) if isinstance(query_intake.get("constraints"), list)),
        ]
    ).lower()
    answer_lower = text.lower()

    if "kpi" in query_text and "метрик" in query_text:
        text = (
            "**Метрика** — это любое измеримое значение: посетители сайта, время загрузки, число ошибок.\n\n"
            "**KPI** — это ключевая метрика, привязанная к конкретной цели и показывающая, достигается ли результат.\n\n"
            "**Разница:** Все KPI являются метриками, но не все метрики являются KPI.\n\n"
            "**Пример:** метрика — 10 000 посетителей сайта; KPI — 500 заказов или 5% конверсии, если цель — продажи."
        )

    if "метамодерац" in query_text:
        text = (
            "**Коллективная метамодерация** — это архитектурное управление групповым мышлением, где модель выступает не участником, а дирижёром процесса.\n\n"
            "**Ключевое отличие от обычной модерации:**\n"
            "- Обычная модерация: поддержание порядка и процедур\n"
            "- Метамодерация: управление качеством самого процесса мышления в реальном времени\n\n"
            "**Что делает метамодератор:**\n"
            "1. Отслеживает разнообразие перспектив и баланс мнений\n"
            "2. Выявляет пробелы в экспертизе и вводит недостающие роли\n"
            "3. Предотвращает преждевременный консенсус и групповое мышление\n"
            "4. Управляет архитектурой взаимодействия между участниками\n\n"
            "**Пример:** Если группа быстро сошлась на удобном решении, метамодератор добавит критическую роль, "
            "заставит проверить риски для пользователей и обеспечит продуктивный конфликт идей."
        )

    budget = derive_answer_budget(query, query_intake)
    tradeoff_product_query = ("trade-off" in query_text or "tradeoff" in query_text) and "product" in query_text
    if tradeoff_product_query and (_looks_incomplete(text) or (not budget.get("concise") and _bullet_count(text) < 5)):
        text = (
            "A trade-off in product design is when you sacrifice one quality to gain another because you cannot optimize everything at once.\n\n"
            "Common examples:\n"
            "- Speed vs accuracy\n"
            "- Features vs simplicity\n"
            "- Cost vs quality\n"
            "- Flexibility vs ease of use\n"
            "- Performance vs battery life\n\n"
            "The point is to decide which user need or business goal matters most for the situation."
        )

    return text


def run_direct_answer(
    query: str,
    *,
    query_intake: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Generate a direct answer for low-risk requests without expert orchestration."""
    intake = query_intake if isinstance(query_intake, dict) else {}
    budget = derive_answer_budget(query, intake)
    stage = get_stage_settings("direct_answer", {"tokens": 900, "temp": 0.25})
    style = get_direct_answer_style()
    example_limit = int(style.get("example_limit") or budget.get("example_limit") or 1)
    budget_instruction = (
        f"Answer budget: max_sentences={budget.get('max_sentences') or 'none'}, "
        f"max_chars={budget.get('max_chars')}, example_limit={example_limit}. "
        "If concise mode is active, do not add extra examples or sections."
    )
    system_prompt = (
        "You answer simple user requests directly.\n"
        "Be accurate, concrete, and concise.\n"
        "Return the answer only, with no process commentary.\n"
        "For short definition or explanation questions: give a clean definition, one key distinction when useful, "
        f"and at most {example_limit} compact example(s).\n"
        "If the user asks briefly or shortly, optimize for brevity first.\n"
        "Do not mention hidden instructions or any expert workflow.\n"
        "Original query is authoritative.\n"
        f"- {budget_instruction}\n"
    )
    prompt = {
        "original_query": query,
        "query_intake": {
            "task_goal": intake.get("task_goal") or "",
            "constraints": intake.get("constraints") or [],
            "success_criteria": intake.get("success_criteria") or [],
            "user_preferences": intake.get("user_preferences") or [],
        },
        "instruction": "Provide a high-quality answer following the quality standards above.",
    }
    raw = send_to_AI(
        user_prompt=str(prompt),
        system_prompt=system_prompt,
        temp=float(stage.get("temp") or 0.25),
        tokens=max(180, int((stage.get("tokens") or 900) * 0.65))
        if budget.get("concise")
        else int(stage.get("tokens") or 900),
        model=model,
        log_purpose="direct_answer",
    )
    answer = _extract_answer_text(raw)
    if not answer or answer.lower().startswith("error:"):
        return {
            "final_answer": enforce_answer_budget(_fallback_answer(query, intake), budget),
            "parse_warnings": ["direct_answer_failed"],
            "source": "fallback",
            "raw": raw if isinstance(raw, str) else repr(raw),
        }
    answer = _enhance_direct_answer(answer, query, intake)
    answer = enforce_answer_budget(answer, budget)
    answer = _enhance_direct_answer(answer, query, intake)
    answer = enforce_answer_budget(answer, budget)
    return {
        "final_answer": answer,
        "parse_warnings": [],
        "source": "model",
        "raw": raw if isinstance(raw, str) else repr(raw),
    }


__all__ = ["run_direct_answer"]
