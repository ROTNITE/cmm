# agent_critic.py - Простой критик планов (только оценка)

import json
from datetime import datetime
from Lib.AI_request import send_to_AI

def criticize_plan(plan, original_query, depth="standard"):
    """
    Только критикует план и возвращает оценку.
    НЕ принимает решение, что делать дальше.
    
    plan - словарь с планом от планировщика
    original_query - исходный вопрос пользователя
    depth - глубина проверки: "quick", "standard", "thorough"
    
    Возвращает словарь с оценками, замечаниями и рекомендациями
    """
    
    print(f"\n🔍 Критик проверяет план для: {original_query[:50]}...")
    
    # Проверяем, что план не пустой
    if not plan:
        return {"error": "Пустой план"}
    
    # Настройки для разной глубины проверки
    settings = {
        "quick": {"tokens": 400, "temp": 0.3},
        "standard": {"tokens": 600, "temp": 0.4},
        "thorough": {"tokens": 800, "temp": 0.5}
    }
    
    # Берём настройки для нужной глубины
    current = settings.get(depth, settings["standard"])
    
    # Превращаем план в текст для отправки ИИ
    plan_text = f"""
ОСНОВНАЯ ИДЕЯ: {plan.get('main_idea', 'Нет главной идеи')}

ШАГИ:
"""
    # Добавляем шаги
    for step in plan.get('steps', [])[:5]:
        if isinstance(step, dict):
            plan_text += f"- {step.get('title', 'Шаг')}\n"
            for substep in step.get('substeps', [])[:3]:
                plan_text += f"  * {substep}\n"
    
    # Добавляем нюансы
    if plan.get('nuances'):
        plan_text += f"\nНЮАНСЫ: {', '.join(plan['nuances'][:3])}\n"
    
    # Добавляем проблемы
    if plan.get('potential_problems'):
        plan_text += f"ПРОБЛЕМЫ: {', '.join(plan['potential_problems'][:3])}\n"
    
    # Системный промпт - объясняем ИИ, что делать
    system_prompt = """Ты критик. Оцени план ответа.

Оцени каждый критерий от 0 до 10:
1. СООТВЕТСТВИЕ - план отвечает на вопрос?
2. ЛОГИЧНОСТЬ - шаги идут по порядку?
3. ПОЛНОТА - всё нужное есть?
4. ПОНЯТНОСТЬ - всё ясно описано?

После оценок напиши:
СИЛЬНЫЕ СТОРОНЫ: (список через дефис)
СЛАБЫЕ СТОРОНЫ: (список через дефис)
РЕКОМЕНДАЦИИ: (что исправить, список через дефис)

ИТОГОВАЯ ОЦЕНКА: (средний балл числом)
"""
    
    # Запрос к ИИ
    user_prompt = f"""Вопрос пользователя: {original_query}

План для оценки:
{plan_text}

Оцени план."""
    
    # Отправляем запрос
    print("🔄 Отправляю запрос к критику...")
    response = send_to_AI(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=current["temp"],
        tokens=current["tokens"]
    )
    
    # Проверяем ответ
    if not response or isinstance(response, Exception):
        print("❌ Ошибка, создаю простую оценку")
        return {
            "scores": {"Соответствие": 5.0, "Логичность": 5.0, "Полнота": 5.0, "Понятность": 5.0},
            "strengths": ["План существует"],
            "weaknesses": ["Не удалось оценить из-за ошибки"],
            "recommendations": ["Попробуйте ещё раз"],
            "final_score": 5.0,
            "timestamp": str(datetime.now())
        }
    
    # Разбираем ответ
    critique = {
        "scores": {},
        "strengths": [],
        "weaknesses": [],
        "recommendations": [],
        "final_score": 0.0,
        "timestamp": str(datetime.now())
    }
    
    # Простой разбор ответа по строкам
    lines = response.split("\n")
    current_section = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Ищем оценки (формат "Название: 7/10")
        if ":" in line and ("/10" in line or "из 10" in line):
            parts = line.split(":", 1)
            name = parts[0].strip()
            # Ищем число в строке
            for word in parts[1].split():
                word = word.replace("/10", "").replace("из 10", "").strip()
                try:
                    score = float(word)
                    if 0 <= score <= 10:
                        critique["scores"][name] = score
                        break
                except:
                    pass
        
        # Ищем секции
        lower = line.lower()
        if "сильные стороны" in lower:
            current_section = "strengths"
        elif "слабые стороны" in lower:
            current_section = "weaknesses"
        elif "рекомендац" in lower:
            current_section = "recommendations"
        elif "итоговая оценка" in lower:
            current_section = "final_score"
            # Ищем число
            for word in line.split():
                try:
                    score = float(word)
                    critique["final_score"] = score
                    break
                except:
                    pass
        
        # Добавляем в текущую секцию
        elif current_section in ["strengths", "weaknesses", "recommendations"]:
            if line.startswith(("-", "•", "*", "1.", "2.")):
                critique[current_section].append(line.lstrip("-•*123456789. ").strip())
    
    # Если не нашли итоговую оценку, считаем среднюю
    if critique["final_score"] == 0.0 and critique["scores"]:
        critique["final_score"] = sum(critique["scores"].values()) / len(critique["scores"])
    
    print(f"✅ Критика готова. Оценка: {critique['final_score']:.1f}/10")
    
    return critique

def show_critique(critique):
    """Показывает результат критики красиво (только для просмотра)"""
    print("\n" + "="*60)
    print("🔍 ОТЧЕТ КРИТИКА")
    print("="*60)
    
    # Оценки по критериям
    if critique.get("scores"):
        print("\n📊 ОЦЕНКИ:")
        for name, score in critique["scores"].items():
            bar = "█" * int(score) + "░" * (10 - int(score))
            print(f"  {name[:15]:15} | {score:.1f}/10 {bar}")
    
    # Итоговая оценка
    print(f"\n🏆 ИТОГОВАЯ ОЦЕНКА: {critique.get('final_score', 0):.1f}/10")
    
    # Сильные стороны
    if critique.get("strengths"):
        print("\n✅ СИЛЬНЫЕ СТОРОНЫ:")
        for s in critique["strengths"][:3]:
            print(f"  • {s}")
    
    # Слабые стороны
    if critique.get("weaknesses"):
        print("\n⚠️ СЛАБЫЕ СТОРОНЫ:")
        for w in critique["weaknesses"][:3]:
            print(f"  • {w}")
    
    # Рекомендации
    if critique.get("recommendations"):
        print("\n💡 РЕКОМЕНДАЦИИ:")
        for r in critique["recommendations"][:3]:
            print(f"  • {r}")
    
    print("\n" + "="*60)


# Тестирование (если файл запущен напрямую)
if __name__ == "__main__":
    print("🔬 ТЕСТИРОВАНИЕ КРИТИКА")
    print("="*60)
    
    # Тестовый план
    test_query = "Как приготовить пасту карбонара?"
    test_plan = {
        "main_idea": "Приготовить пасту карбонара",
        "steps": [
            {"number": "1", "title": "Подготовить продукты", "substeps": ["Паста", "Яйца", "Бекон", "Сыр"]},
            {"number": "2", "title": "Сварить пасту", "substeps": ["Вскипятить воду", "Посолить", "Варить 8 минут"]},
            {"number": "3", "title": "Приготовить соус", "substeps": ["Обжарить бекон", "Смешать яйца с сыром"]}
        ],
        "nuances": ["Не перегреть яйца"],
        "potential_problems": ["Яйца могут свернуться"]
    }
    
    # Проверяем план
    result = criticize_plan(test_plan, test_query)
    show_critique(result)
