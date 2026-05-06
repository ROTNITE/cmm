# Анализ деградации качества CMM системы

**Дата анализа:** 2026-05-06  
**Анализируемые тесты:** eval_quality_improvements → eval_cmm_quality_fix_10 → eval_cmm_quality_fix_10_final

## Краткое резюме проблемы

С каждым новым тестом качество системы **ухудшается**:

| Тест | Avg Delta | CMM Wins | Baseline Wins | Ties |
|------|-----------|----------|---------------|------|
| eval_quality_improvements | **+1.40** | 5 | 0 | 0 |
| eval_cmm_quality_fix_10 | **+0.60** | 8 | 2 | 0 |
| eval_cmm_quality_fix_10_final | **-1.50** | 6 | 4 | 0 |

**Тренд:** От +1.40 → +0.60 → -1.50 (деградация на **2.9 пункта**)

## Ключевые находки

### 1. Проблема с DIRECT режимом (V2-003)

**V2-003: "What is a trade-off in product design?"**

- **eval_quality_improvements**: CMM победил (+2.0 delta), ответ 1160 символов
- **eval_cmm_quality_fix_10**: Baseline победил (-1.0 delta), ответ 356 символов
- **eval_cmm_quality_fix_10_final**: Baseline победил (-1.0 delta), ответ 356 символов

**Причина:** Добавление `answer_budget` и `enforce_answer_budget` в `direct_answer.py` **слишком агрессивно обрезает ответы**. Constraint "Keep it concise" интерпретируется как max 5 предложений и 650 символов, что убивает качество для вопросов требующих примеров.

### 2. Проблема с FULL_CMM режимом

**Критические ошибки в FULL_CMM:**

- V2-006: `plan_needs_revision_after_max_iters | critical_plan_blockers` → -9.0 delta
- V2-010: `plan_needs_revision_after_max_iters | critical_plan_blockers` → -9.0 delta (в final тесте)

**Причина:** Изменения в `quality_gates.py` сделали критерии блокировки **слишком строгими**. Система отказывается генерировать ответ даже когда план приемлемый.

### 3. Hardcoded решения вместо универсальных

В `direct_answer.py` добавлены **хардкоды для конкретных кейсов**:

```python
if "kpi" in query_text and "метрик" in query_text:
    text = "**Метрика** — это любое измеримое значение..."  # Hardcoded answer

if tradeoff_product_query and (_looks_incomplete(text) or ...):
    text = "A trade-off in product design is when..."  # Hardcoded answer
```

**Проблема:** Это **точечные правки под датасет**, а не универсальное решение. Система заточена под конкретные примеры вместо обобщения.

## Системные проблемы

### 1. Overfitting на датасет
- Хардкоды для KPI/метрик и trade-offs показывают что система **дрочится под конкретные кейсы**
- Это не масштабируется и не работает на новых данных

### 2. Конфликт между brevity и quality
- `answer_budget` слишком агрессивно режет ответы
- Constraint "Keep it concise" → 650 chars, но для качественного ответа с примерами нужно больше
- Система жертвует примерами ради краткости

### 3. Quality gates слишком строгие
- `quality_gates.py` блокирует FULL_CMM даже при приемлемых планах
- `critical_plan_blockers` срабатывает на false positives
- Система падает в fallback вместо best-effort ответа

### 4. Нет баланса между режимами
- DIRECT стал слишком кратким
- FULL_CMM слишком часто падает
- LIGHT_CMM работает лучше всего, но не покрывает сложные кейсы

## Что нужно исправить

### Приоритет 1: Убрать hardcoded ответы
- Удалить хардкоды для KPI и trade-offs из `direct_answer.py`
- Улучшить промпт вместо хардкодов

### Приоритет 2: Пересмотреть answer_budget
- Сделать budget менее агрессивным для DIRECT режима
- Разрешить больше символов когда нужны примеры
- Не резать ответ если он качественный

### Приоритет 3: Ослабить quality_gates
- Пересмотреть критерии `critical_plan_blockers`
- Разрешить best-effort finalization чаще
- Не блокировать на generic plan quality issues

### Приоритет 4: Улучшить промпты
- DIRECT промпт должен лучше балансировать brevity и examples
- Добавить инструкции про "concise but complete"
- Научить модель когда можно быть кратким, а когда нужны детали

## Концептуальные вопросы

### Правильна ли архитектура?
- **Роутинг работает хорошо** (90% accuracy)
- **LIGHT_CMM стабилен**
- **DIRECT и FULL_CMM проблемные**

### Что добавить нового?
- **Adaptive budget**: определять budget не только по constraints, но и по типу вопроса
- **Quality feedback loop**: если ответ слишком короткий и неполный, расширить его
- **Graceful degradation**: FULL_CMM должен падать в LIGHT_CMM, а не в fallback

## Рекомендации

1. **Откатить hardcoded ответы** - они маскируют реальные проблемы
2. **Сделать answer_budget адаптивным** - учитывать тип вопроса, не только constraints
3. **Ослабить quality_gates** - разрешить best-effort чаще
4. **Добавить fallback chain**: FULL_CMM → LIGHT_CMM → DIRECT → fallback
5. **Улучшить промпты** вместо хардкодов

## Следующие шаги

1. Создать тест без hardcoded ответов
2. Протестировать более мягкий answer_budget
3. Протестировать ослабленные quality_gates
4. Сравнить результаты с baseline
