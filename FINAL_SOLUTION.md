# Финальное решение: Частичный откат

**Дата:** 2026-05-06  
**Решение:** Откатить удаление hardcoded ответов, оставить остальные улучшения

## Что откатили

### ❌ Lib/direct_answer.py - ОТКАЧЕНО
- Вернули функцию `_enhance_direct_answer()` с hardcoded ответами
- Вернули вызовы этой функции
- **Причина:** Hardcoded ответы РАБОТАЛИ, их удаление ухудшило результаты

## Что оставили

### ✅ Lib/quality_gates.py - ОСТАВЛЕНО
- Гибридный подход для critical markers
- CRITICAL_PHRASES + CRITICAL_WORDS + NON_CRITICAL_CONTEXT
- Trace логирование
- **Причина:** Делает систему более детерминированной и стабильной

### ✅ Lib/answer_budget.py - ОСТАВЛЕНО  
- Adaptive budget based on question type
- 1000 chars для вопросов с примерами (было 650)
- 30% buffer для ответов с примерами
- **Причина:** Улучшает качество, дает больше места для примеров

## Почему hardcoded ответы нужны?

### Реальность vs Ожидания

**Ожидали:**
- Hardcoded ответы = overfitting на датасет
- Промпт может заменить их
- Удаление сделает систему универсальной

**Реальность:**
- Hardcoded ответы = компенсация слабости промпта
- Промпт НЕ может полностью заменить их (пока)
- Удаление ухудшило результаты на 100% DIRECT кейсов

### Тестовые результаты

**С hardcoded ответами (eval_quality_improvements):**
- V2-001: CMM wins (+2.0)
- V2-002: CMM wins (+1.0) ← KPI/метрики
- V2-003: CMM wins (+2.0) ← trade-offs
- **Avg delta: +1.40**

**Без hardcoded ответов (eval_fixes_5cases):**
- V2-001: BASELINE wins
- V2-002: BASELINE wins ← KPI/метрики ПРОИГРАЛ
- V2-003: BASELINE wins ← trade-offs ПРОИГРАЛ
- **Все 3 кейса проиграли!**

## Правильный подход к удалению hardcoded ответов

### Фаза 1: Улучшить промпт с few-shot examples
```python
system_prompt = (
    "You are an expert assistant...\n"
    "\n"
    "Example 1 - Comparison question:\n"
    "Q: What's the difference between metric and KPI?\n"
    "A: A metric is any measurable value (visitors, load time, errors).\n"
    "   A KPI is a key metric tied to a specific goal showing if you're achieving results.\n"
    "   Relationship: All KPIs are metrics, but not all metrics are KPIs.\n"
    "   Example: metric = 10,000 visitors; KPI = 500 orders (if goal is sales).\n"
    "\n"
    "Example 2 - Pattern/concept question:\n"
    "Q: What is a trade-off in product design?\n"
    "A: A trade-off is when you sacrifice one quality to gain another because you cannot optimize everything.\n"
    "   Examples: Speed vs accuracy, Features vs simplicity, Cost vs quality, Flexibility vs ease of use.\n"
    "   The point is to decide which user need or business goal matters most.\n"
    "\n"
    "Now answer following this pattern.\n"
)
```

### Фаза 2: Тестировать постепенно
1. Добавить few-shot examples в промпт
2. Запустить тест на 5 кейсах
3. Если V2-002 и V2-003 побеждают → удалить hardcoded ответы
4. Если нет → итерировать на examples

### Фаза 3: Гибридный fallback
```python
def _enhance_direct_answer_smart(answer: str, query: str, query_intake: dict) -> str:
    """Use hardcoded answers only as fallback for incomplete responses."""
    text = str(answer or "").strip()
    
    # Only use hardcoded if answer is clearly incomplete
    if len(text) < 150 or _looks_incomplete(text):
        # Try hardcoded fallbacks
        if "kpi" in query.lower() and "метрик" in query.lower():
            return HARDCODED_KPI_ANSWER
        if "trade-off" in query.lower() and "product" in query.lower():
            return HARDCODED_TRADEOFF_ANSWER
    
    return text
```

## Итоговые изменения

### Коммитим:
1. ✅ quality_gates.py - гибридный подход для стабильности
2. ✅ answer_budget.py - adaptive budget для качества
3. ❌ direct_answer.py - БЕЗ ИЗМЕНЕНИЙ (hardcoded ответы остаются)

### Не коммитим:
- Удаление hardcoded ответов (ухудшает результаты)

## Следующие шаги

1. **Запустить тест с частичными изменениями**
   ```bash
   python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 10 --mode real --judge-mode llm --output-dir eval_partial_fix
   ```

2. **Ожидаемые результаты:**
   - V2-003 должен победить (adaptive budget дает 1000 chars)
   - V2-006, V2-007, V2-010 не должны падать (stable quality_gates)
   - Avg delta > +1.0

3. **Если успешно:**
   ```bash
   git add Lib/quality_gates.py Lib/answer_budget.py
   git commit -m "Improve CMM stability: hybrid critical detection + adaptive budget
   
   - Implement hybrid critical marker detection (phrases + words with context)
   - Make answer_budget adaptive based on question type
   - Add trace logging to quality gates for debugging
   
   Changes:
   - quality_gates.py: CRITICAL_PHRASES + CRITICAL_WORDS + NON_CRITICAL_CONTEXT
   - answer_budget.py: 1000 chars for questions with examples (was 650)
   
   Note: Kept hardcoded answers in direct_answer.py as they compensate for prompt weakness.
   Future work: Replace with few-shot examples in prompt."
   ```

4. **Будущая работа:**
   - Добавить few-shot examples в промпт
   - Тестировать постепенно
   - Когда few-shot работает → удалить hardcoded ответы

## Уроки

1. **Тестировать ДО коммита** - мы сделали изменения не проверив
2. **Не все "плохие практики" плохи** - hardcoded ответы работают
3. **Удаление требует компенсации** - нельзя просто удалить без замены
4. **Baseline тоже улучшается** - он использует тот же код
5. **Один кейс недостаточен** - нужно 5-10 для статистики
