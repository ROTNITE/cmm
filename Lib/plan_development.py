# agent_planner.py - планировщик

import json
from datetime import datetime
from Lib.json_retry import call_json_model
from Lib.json_utils import to_string_list


def _context_items(context, section, key, max_items=5):
    if not isinstance(context, dict):
        return []
    source = context.get(section) if isinstance(context.get(section), dict) else {}
    return to_string_list(source.get(key), max_items=max_items)


def _fallback_steps(context):
    constraints = _context_items(context, "query_intake", "constraints", 5)
    success_criteria = _context_items(context, "query_intake", "success_criteria", 5)
    must_address = _context_items(context, "deliberation_brief", "must_address", 5)
    blind_spots = _context_items(context, "conflict_report", "blind_spots", 5)
    tradeoffs = _context_items(context, "conflict_report", "unresolved_tradeoffs", 5)

    steps = [
        {
            "number": "1",
            "title": "Сформулировать цель и рабочий контекст запроса",
            "substeps": [],
            "uses_expert_inputs": [],
        }
    ]
    if constraints:
        steps.append(
            {
                "number": str(len(steps) + 1),
                "title": "Проверить решение против ограничений",
                "substeps": constraints,
                "uses_expert_inputs": constraints,
            }
        )
    if must_address or blind_spots or tradeoffs:
        items = must_address + blind_spots + [str(item) for item in tradeoffs]
        steps.append(
            {
                "number": str(len(steps) + 1),
                "title": "Закрыть обязательные риски, blind spots и trade-offs",
                "substeps": items[:8],
                "uses_expert_inputs": items[:8],
            }
        )
    if success_criteria:
        steps.append(
            {
                "number": str(len(steps) + 1),
                "title": "Связать рекомендации с критериями успеха",
                "substeps": success_criteria,
                "uses_expert_inputs": success_criteria,
            }
        )
    steps.append(
        {
            "number": str(len(steps) + 1),
            "title": "Подготовить итоговый ответ с реалистичными шагами и оговорками",
            "substeps": [],
            "uses_expert_inputs": [],
        }
    )
    return steps


def _fallback_plan(
    query,
    depth="detailed",
    warning="model_response_unavailable",
    *,
    context=None,
    extra_warnings=None,
    json_attempts=0,
):
    return {
        "query": query,
        "main_idea": f"Ответить на: {query}",
        "preparation": [],
        "steps": _fallback_steps(context),
        "nuances": [],
        "potential_problems": _context_items(context, "deliberation_brief", "expert_risks", 6)
        + _context_items(context, "conflict_report", "blind_spots", 6),
        "result": "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": [warning] + list(extra_warnings or []),
        "json_attempts": int(json_attempts or 0),
        "raw_format": "fallback",
        "source": "fallback",
    }


def _normalize_step(item, index):
    if not isinstance(item, dict):
        return None

    number = item.get("number")
    if not isinstance(number, str) or not number.strip():
        number = str(index)

    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    return {
        "number": number.strip(),
        "title": title.strip(),
        "substeps": to_string_list(item.get("substeps"), max_items=8),
        "uses_expert_inputs": to_string_list(item.get("uses_expert_inputs"), max_items=6),
    }


def _normalize_json_plan(payload, query, depth):
    if not isinstance(payload, dict):
        return None

    steps_raw = payload.get("steps")
    steps = []
    if isinstance(steps_raw, list):
        for index, item in enumerate(steps_raw, start=1):
            step = _normalize_step(item, index)
            if step:
                steps.append(step)

    main_idea = payload.get("main_idea")
    result = payload.get("result")

    plan = {
        "query": query,
        "main_idea": main_idea.strip() if isinstance(main_idea, str) else "",
        "preparation": to_string_list(payload.get("preparation"), max_items=10),
        "steps": steps,
        "nuances": to_string_list(payload.get("nuances"), max_items=10),
        "potential_problems": to_string_list(payload.get("potential_problems"), max_items=10),
        "result": result.strip() if isinstance(result, str) else "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": [],
        "raw_format": "json",
    }

    if not plan["main_idea"] and not plan["steps"]:
        return None

    return plan


def _parse_legacy_text_plan(response, query, depth, context=None):
    plan = {
        "query": query,
        "main_idea": "",
        "preparation": [],
        "steps": [],
        "nuances": [],
        "potential_problems": [],
        "result": "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": ["json_parse_failed; used legacy text parser"],
        "json_attempts": 0,
        "raw_format": "legacy_text",
        "source": "legacy_text",
    }

    current_section = ""
    current_step = None

    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "ОСНОВНАЯ ИДЕЯ" in line.upper():
            current_section = "main_idea"
            if ":" in line:
                plan["main_idea"] = line.split(":", 1)[1].strip()
        elif "ПОДГОТОВКА" in line.upper():
            current_section = "preparation"
        elif "ШАГИ" in line.upper():
            current_section = "steps"
        elif "НЮАНСЫ" in line.upper():
            current_section = "nuances"
        elif "РЕЗУЛЬТАТ" in line.upper():
            current_section = "result"
        else:
            if current_section == "main_idea" and not plan["main_idea"]:
                plan["main_idea"] = line
            elif current_section == "preparation" and line.startswith("-"):
                plan["preparation"].append(line.lstrip("- "))
            elif current_section == "steps":
                if line[0].isdigit() and "." in line:
                    if current_step:
                        plan["steps"].append(current_step)
                    parts = line.split(".", 1)
                    current_step = {
                        "number": parts[0],
                        "title": parts[1].strip(),
                        "substeps": [],
                        "uses_expert_inputs": [],
                    }
                elif line.startswith("-") and current_step:
                    current_step["substeps"].append(line.lstrip("- "))
            elif current_section == "nuances" and line.startswith("-"):
                plan["nuances"].append(line.lstrip("- "))
            elif current_section == "result" and not plan["result"]:
                plan["result"] = line

    if current_step and current_step not in plan["steps"]:
        plan["steps"].append(current_step)

    if not plan["main_idea"] and not plan["steps"]:
        return _fallback_plan(
            query,
            depth=depth,
            warning="json_and_legacy_plan_parse_failed",
            context=context,
        )

    return plan

def develop_plan(query, context=None, depth="detailed", model="deepseek-chat"):
    """
    Создаёт план ответа на запрос.

    query - вопрос пользователя
    context - дополнительная информация (необязательно)
    depth - глубина плана: "quick", "detailed", "comprehensive"
    model - model name forwarded to the configured AI provider
    """

    # Проверяем, что запрос не пустой
    if not query:
        return {"error": "Пустой запрос"}

    # Настройки для разной глубины плана
    settings = {
        "quick": {"tokens": 400, "temp": 0.3},
        "detailed": {"tokens": 800, "temp": 0.4},
        "comprehensive": {"tokens": 1200, "temp": 0.5}
    }

    # Берём настройки для нужной глубины, если нет - используем detailed
    current = settings.get(depth, settings["detailed"])

    system_prompt = """Ты планировщик. Создай план ответа.
Original query is authoritative. Cleaned/formalized query is helper text only. Do not ignore constraints from original_query.
CRITICAL: Return ONLY valid JSON. No markdown blocks. No comments. No extra text.
CRITICAL: Close all brackets and braces properly.
Schema:
{
  "main_idea": "string",
  "preparation": ["string"],
  "steps": [
    {
      "number": "1",
      "title": "string",
      "substeps": ["string"],
      "uses_expert_inputs": ["string"]
    }
  ],
  "nuances": ["string"],
  "potential_problems": ["string"],
  "result": "string"
}
"""

    # Добавляем контекст, если есть
    context_text = ""
    if context:
        context_text = f"\nКонтекст: {json.dumps(context, ensure_ascii=False)}"

    # Запрос к ИИ
    user_prompt = f"Составь план для вопроса: {query}{context_text}"

    result = call_json_model(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=current["temp"],
        tokens=current["tokens"],
        model=model,
        max_retries=1,
    )

    payload = result.get("payload") if isinstance(result, dict) else None
    warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    plan = _normalize_json_plan(payload, query=query, depth=depth)
    if plan is not None:
        plan["parse_warnings"] = warnings
        plan["json_attempts"] = attempts
        plan["source"] = "model"
        return plan

    plan = _parse_legacy_text_plan(raw, query=query, depth=depth, context=context)
    plan["parse_warnings"] = list(plan.get("parse_warnings", [])) + warnings
    plan["json_attempts"] = attempts
    if plan.get("raw_format") == "fallback":
        plan["source"] = "fallback"

    return plan

def show_plan(plan):
    """Manual display helper for local scripts."""
    print("\n" + "="*50)
    print("📋 ПЛАН")
    print("="*50)

    if plan.get("main_idea"):
        print(f"\n🎯 ИДЕЯ: {plan['main_idea']}")

    if plan.get("preparation"):
        print("\n📦 ПОДГОТОВКА:")
        for item in plan["preparation"]:
            print(f"  • {item}")

    if plan.get("steps"):
        print("\n📝 ШАГИ:")
        for step in plan["steps"]:
            print(f"\n  {step['number']}. {step['title']}")
            for substep in step.get("substeps", []):
                print(f"     • {substep}")

    if plan.get("nuances"):
        print("\n⚠️ НЮАНСЫ:")
        for item in plan["nuances"]:
            print(f"  • {item}")

    if plan.get("result"):
        print(f"\n✨ РЕЗУЛЬТАТ: {plan['result']}")

    print("\n" + "="*50)

# Простой способ использовать планировщик
if __name__ == "__main__":
    # Тестовые запросы
    tests = [
        "Как научиться программировать?",
        "Что лучше: Python или JavaScript?"
    ]

    for test in tests:
        print(f"\n\n📝 Тест: {test}")
        plan = develop_plan(test, depth="quick")
        show_plan(plan)
        input("\nНажми Enter для следующего теста...")
