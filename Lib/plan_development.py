# agent_planner.py - планировщик

import json
from datetime import datetime
from Lib.AI_request import send_to_AI
from Lib.json_utils import safe_json_loads, to_string_list


def _fallback_plan(query, depth="detailed", warning="model_response_unavailable"):
    return {
        "query": query,
        "main_idea": f"Ответить на: {query}",
        "preparation": [],
        "steps": [
            {"number": "1", "title": "Разобраться в вопросе", "substeps": [], "uses_expert_inputs": []},
            {"number": "2", "title": "Учесть контекст и ограничения", "substeps": [], "uses_expert_inputs": []},
            {"number": "3", "title": "Подготовить ответ", "substeps": [], "uses_expert_inputs": []},
        ],
        "nuances": [],
        "potential_problems": [],
        "result": "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": [warning],
        "raw_format": "fallback",
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


def _parse_legacy_text_plan(response, query, depth):
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
        "raw_format": "legacy_text",
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
        return _fallback_plan(query, depth=depth, warning="json_and_legacy_plan_parse_failed")

    return plan

def develop_plan(query, context=None, depth="detailed"):
    """
    Создаёт план ответа на запрос.

    query - вопрос пользователя
    context - дополнительная информация (необязательно)
    depth - глубина плана: "quick", "detailed", "comprehensive"
    """

    # Проверяем, что запрос не пустой
    if not query:
        return {"error": "Пустой запрос"}

    # Настройки для разной глубины плана
    settings = {
        "quick": {"tokens": 300, "temp": 0.3},
        "detailed": {"tokens": 600, "temp": 0.5},
        "comprehensive": {"tokens": 1000, "temp": 0.7}
    }

    # Берём настройки для нужной глубины, если нет - используем detailed
    current = settings.get(depth, settings["detailed"])

    system_prompt = """Ты планировщик. Создай план ответа.
Original query is authoritative. Cleaned/formalized query is helper text only. Do not ignore constraints from original_query.
Верни СТРОГО JSON без markdown, пояснений и лишнего текста.
Схема:
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

    response = send_to_AI(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=current["temp"],
        tokens=current["tokens"]
    )

    if not response or isinstance(response, Exception):
        return _fallback_plan(query, depth=depth)

    parsed = safe_json_loads(response)
    plan = _normalize_json_plan(parsed, query=query, depth=depth)
    if plan is None:
        plan = _parse_legacy_text_plan(response, query=query, depth=depth)

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
