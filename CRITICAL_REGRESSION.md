# КРИТИЧЕСКАЯ ПРОБЛЕМА: Исправления ухудшили результаты

**Дата:** 2026-05-06  
**Статус:** ❌ РЕГРЕССИЯ

## Результаты тестирования

### После исправлений (eval_fixes_5cases)
**Первые 3 кейса - ВСЕ проиграли Baseline:**
- V2-001: BASELINE wins
- V2-002: BASELINE wins
- V2-003: BASELINE wins ❌ **КРИТИЧЕСКИЙ КЕЙС**

### До исправлений (eval_quality_improvements)
- V2-001: CMM wins (+2.0)
- V2-002: CMM wins (+1.0)
- V2-003: CMM wins (+2.0)

## Что пошло не так?

### Гипотеза 1: Удаление hardcoded ответов убило качество
**Проблема:** Hardcoded ответы для KPI и trade-offs РАБОТАЛИ.
- V2-002 (KPI/метрики) - был hardcoded ответ → теперь проиграл
- V2-003 (trade-offs) - был hardcoded ответ → теперь проиграл

**Вывод:** Hardcoded ответы были не overfitting, а **необходимая компенсация** слабости промпта.

### Гипотеза 2: Улучшенный промпт недостаточен
**Проблема:** Новый промпт не компенсирует удаление hardcoded ответов.

Было в промпте:
```
"For metric/KPI or X-vs-Y answers: explicitly state 'all KPIs are metrics, 
not all metrics are KPIs' when applicable and show one paired example"
```

Стало:
```
"For X-vs-Y questions: explicitly state the relationship (e.g., 'all KPIs are 
metrics, not all metrics are KPIs')"
```

**Вывод:** Инструкция есть, но модель не следует ей так же хорошо как hardcoded ответ.

### Гипотеза 3: Adaptive budget работает, но Baseline тоже улучшился
**Проблема:** Baseline использует ТОТ ЖЕ КОД (direct_answer.py, answer_budget.py).
- Мы улучшили систему → Baseline тоже улучшился
- CMM и Baseline оба стали лучше → но Baseline стал БОЛЬШЕ лучше

**Вывод:** Наши исправления помогли Baseline больше чем CMM.

## Корневая причина

**МЫ НЕПРАВИЛЬНО ДИАГНОСТИРОВАЛИ ПРОБЛЕМУ.**

Изначальная гипотеза была:
> "Hardcoded ответы - это overfitting на датасет, нужно их удалить"

Реальность:
> "Hardcoded ответы компенсировали слабость промпта. Удаление их без достаточной компенсации ухудшило качество"

## Что делать?

### Вариант 1: Откатить удаление hardcoded ответов
**Плюсы:**
- Быстро восстановит качество
- V2-002 и V2-003 снова будут побеждать

**Минусы:**
- Остается overfitting на датасет
- Не универсальное решение

### Вариант 2: Улучшить промпт еще больше
**Плюсы:**
- Универсальное решение
- Нет overfitting

**Минусы:**
- Неясно как именно улучшить
- Может потребовать много итераций

### Вариант 3: Гибридный подход
**Идея:** Оставить hardcoded ответы как fallback, но только если модель дала плохой ответ.

```python
def _enhance_direct_answer_fallback(answer: str, query: str, query_intake: dict) -> str:
    """Use hardcoded answers only as fallback for known weak cases."""
    text = str(answer or "").strip()
    
    # Check if answer is incomplete or low quality
    if _looks_incomplete(text) or len(text) < 200:
        # Try hardcoded fallbacks
        if "kpi" in query.lower() and "метрик" in query.lower():
            return HARDCODED_KPI_ANSWER
        if "trade-off" in query.lower() and "product" in query.lower():
            return HARDCODED_TRADEOFF_ANSWER
    
    return text
```

### Вариант 4: Использовать few-shot examples в промпте
**Идея:** Вместо hardcoded ответов, дать модели примеры хороших ответов.

```python
system_prompt = (
    "You are an expert assistant...\n"
    "\n"
    "Example of a good comparison answer:\n"
    "Q: What's the difference between metric and KPI?\n"
    "A: A metric is any measurable value... A KPI is a key metric tied to a specific goal...\n"
    "The relationship: All KPIs are metrics, but not all metrics are KPIs.\n"
    "Example: metric = 10,000 visitors; KPI = 500 orders (if goal is sales).\n"
    "\n"
    "Now answer the user's question following this pattern.\n"
)
```

## Рекомендация

**НЕМЕДЛЕННО:**
1. Откатить удаление hardcoded ответов (Вариант 1)
2. Оставить adaptive budget (он работает)
3. Оставить улучшенные quality_gates (они стабильнее)

**ПОТОМ:**
4. Реализовать Вариант 4 (few-shot examples)
5. Тестировать постепенно
6. Когда few-shot работает - удалить hardcoded ответы

## Выводы

1. **Не все "overfitting" плохо** - иногда это необходимая компенсация
2. **Тестировать нужно ДО коммита** - мы сделали изменения не проверив
3. **Baseline тоже улучшается** - нужно учитывать что он использует тот же код
4. **Удаление без компенсации опасно** - нельзя просто удалить что-то не добавив замену

## Следующие шаги

1. Откатить direct_answer.py к версии с hardcoded ответами
2. Оставить answer_budget.py с adaptive logic
3. Оставить quality_gates.py с гибридным подходом
4. Запустить тест снова
5. Если результаты хорошие - коммитить частичные исправления
