# critic_decision.py - Принимает решения на основе критики

from Lib.agent_critic import criticize_plan, show_critique
from datetime import datetime

def decide_on_critique(plan, original_query, min_score=0.7, depth="standard"):
    """
    Критикует план И принимает решение, что с ним делать.
    
    plan - словарь с планом
    original_query - исходный вопрос
    min_score - минимальный проходной балл (0.0 - 1.0, где 1.0 = 10/10)
    depth - глубина проверки
    
    Возвращает:
        - decision: "ACCEPT", "REJECT", "REVISE"
        - critique: результаты критики
        - message: пояснение
    """
    
    print(f"\n📊 Принимаю решение по плану...")
    
    # 1. Получаем критику (вызываем функцию из другого файла)
    critique = criticize_plan(plan, original_query, depth)
    
    # Проверяем на ошибку
    if "error" in critique:
        return {
            "decision": "REJECT",
            "critique": critique,
            "message": f"Ошибка: {critique['error']}",
            "timestamp": str(datetime.now())
        }
    
    # 2. Принимаем решение на основе оценки
    final_score = critique.get("final_score", 0) / 10  # переводим 8/10 → 0.8
    
    # Проверяем по баллам
    if final_score >= min_score:
        decision = "ACCEPT"
        message = f"План принят (оценка {final_score:.1f} >= {min_score})"
    else:
        # Если баллы низкие, смотрим на рекомендации
        if critique.get("weaknesses") and len(critique["weaknesses"]) > 3:
            decision = "REJECT"
            message = f"План отклонён: слишком много слабых сторон"
        else:
            decision = "REVISE"
            message = f"План нужно доработать (оценка {final_score:.1f} < {min_score})"
    
    # 3. Возвращаем результат
    result = {
        "decision": decision,
        "critique": critique,
        "final_score": final_score,
        "message": message,
        "timestamp": str(datetime.now())
    }
    
    # Показываем результат
    print(f"\n🎯 РЕШЕНИЕ: {decision}")
    print(f"   {message}")
    
    return result

def check_plan_and_act(plan, query, min_score=0.7):
    """
    Проверяет план и говорит, что делать дальше.
    """
    result = decide_on_critique(plan, query, min_score)
    
    # В зависимости от решения
    if result["decision"] == "ACCEPT":
        print("\n✅ План готов! Можно передавать следующему агенту.")
        return {
            "status": "ready",
            "plan": plan,
            "critique": result["critique"]
        }
    
    elif result["decision"] == "REVISE":
        print("\n🔄 План нужно доработать.")
        print("\n📝 Что исправить:")
        for rec in result["critique"].get("recommendations", [])[:3]:
            print(f"  • {rec}")
        
        return {
            "status": "needs_revision",
            "plan": plan,
            "critique": result["critique"],
            "feedback": result["critique"].get("recommendations", [])
        }
    
    else:  # REJECT
        print("\n❌ План отклонён. Нужно начинать заново.")
        return {
            "status": "rejected",
            "plan": plan,
            "critique": result["critique"],
            "reason": "Слишком много проблем"
        }

def quick_decision(plan, query):
    """Быстрое принятие решения"""
    result = decide_on_critique(plan, query, depth="quick")
    show_critique(result["critique"])
    return result


# Тестирование
if __name__ == "__main__":
    print("📊 ТЕСТИРОВАНИЕ ПРИНЯТИЯ РЕШЕНИЙ")
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
    
    # Принимаем решение
    result = check_plan_and_act(test_plan, test_query, min_score=0.7)
    
    print(f"\n📌 Итоговый статус: {result['status']}")
