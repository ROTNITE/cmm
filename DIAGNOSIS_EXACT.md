# Точная диагностика деградации качества CMM

**Дата:** 2026-05-06  
**Метод:** Сравнение git diff + анализ trace данных

## Найденная причина деградации

### Проблема 1: Изменения в quality_gates.py (ГЛАВНАЯ ПРИЧИНА)

**Коммит:** Между eval_cmm_quality_fix_10 и eval_cmm_quality_fix_10_final

**Что изменилось:**

#### 1.1. CRITICAL_MARKERS стали более специфичными

**Было (старые маркеры):**
```python
CRITICAL_MARKERS = (
    "critical", "safety", "security", "privacy", "legal", "compliance",
    "harm", "unsafe", "danger", "failure", "irreversible", ...
)
```

**Стало (новые маркеры):**
```python
CRITICAL_MARKERS = (
    "unsafe", "harmful", "safety issue", "danger", "illegal", "unlawful",
    "violates law", "legal compliance issue", "privacy leak", "data leak",
    "gdpr violation", "hipaa violation", "security exploit", ...
)
```

**Эффект:**
- **Удалены GENERIC слова:** `"critical"`, `"safety"`, `"security"`, `"privacy"`, `"legal"`, `"compliance"`, `"failure"`
- **Добавлены SPECIFIC фразы:** `"safety issue"`, `"legal compliance issue"`, `"privacy leak"`

**Проблема:** Это изменение **НЕПРЕДСКАЗУЕМО**:
- Если модератор пишет "legal issue" → НЕ триггерит (нет слова "legal")
- Если модератор пишет "legal compliance issue" → триггерит
- Если модератор пишет "compliance problem" → НЕ триггерит

**Результат:** Система стала **чувствительна к формулировкам модели**, а не к смыслу.

#### 1.2. has_critical_answer_blockers() изменена

**Было:**
```python
def has_critical_answer_blockers(moderated_result: Any) -> bool:
    normalized = normalize_moderated_result(moderated_result)
    if normalized.get("final_decision") == "REJECT":
        return True  # Любой REJECT блокирует
    if normalized.get("rejected"):
        return True
    # ... проверка critical_issues
```

**Стало:**
```python
def has_critical_answer_blockers(moderated_result: Any) -> bool:
    normalized = normalize_moderated_result(moderated_result)
    # REJECT больше не блокирует автоматически!
    if _safe_list(normalized.get("critical_issues")):
        return True  # Только если есть critical_issues
    # ...
```

**Эффект:**
- **Раньше:** REJECT → автоматический блокер
- **Теперь:** REJECT → блокирует только если есть critical_issues в списке

**Проблема:** Если модератор возвращает `decision: REJECT` но `critical_issues: []` пустой, система **НЕ блокирует**.

### Проблема 2: Недетерминированность модератора

**V2-007 деградация:**
- **eval_cmm_quality_fix_10:** FINALIZE, CMM wins (+1.0)
- **eval_cmm_quality_fix_10_final:** FAILED, critical_answer_moderation_issues (-9.0)

**Что произошло:**
1. Модератор в разных запусках возвращает **разные формулировки**
2. В первом тесте: модератор не нашел critical issues → FINALIZE
3. Во втором тесте: модератор нашел что-то и написал фразу с "legal" или "compliance" → но из-за новых маркеров это НЕ сработало как critical
4. Но state_machine все равно заблокировал из-за другой логики

**Trace показывает:** `cmm_trace` пустой для V2-007 в final тесте, что означает система упала на раннем этапе.

### Проблема 3: Изменения в direct_answer.py

**Добавлено:**
- `answer_budget` логика
- `enforce_answer_budget()` обрезка
- Hardcoded ответы для KPI и trade-offs

**Эффект на V2-003:**
- **eval_quality_improvements:** 1160 chars, CMM wins (+2.0)
- **eval_cmm_quality_fix_10:** 356 chars, Baseline wins (-1.0)
- **eval_cmm_quality_fix_10_final:** 356 chars, Baseline wins (-1.0)

**Причина:** Constraint "Keep it concise" → budget 650 chars → ответ обрезан → потеряны примеры → качество упало.

## Точная причина каждой деградации

### V2-003: DIRECT режим
- **Причина:** answer_budget слишком агрессивный (650 chars для "concise")
- **Решение:** Увеличить budget для вопросов требующих примеры (1000+ chars)

### V2-006: FULL_CMM
- **Причина:** `plan_needs_revision_after_max_iters` + `critical_plan_blockers`
- **Детали:** План не прошел critique после max iterations, система решила что это critical blocker
- **Решение:** Разрешить best-effort finalization если план actionable

### V2-007: LIGHT_CMM → FAILED
- **Причина:** `critical_answer_moderation_issues` 
- **Детали:** Модератор в этом запуске нашел что-то критическое, но из-за изменений в CRITICAL_MARKERS логика сработала непредсказуемо
- **Решение:** Вернуть более стабильную логику critical detection

### V2-010: FULL_CMM
- **Причина:** То же что V2-006 - `plan_needs_revision_after_max_iters` + `critical_plan_blockers`
- **Решение:** То же что для V2-006

## Корневая проблема

**Изменения в quality_gates.py сделали систему НЕДЕТЕРМИНИРОВАННОЙ:**

1. **Зависимость от формулировок модели:** Если модератор пишет "legal issue" vs "legal compliance issue" → разный результат
2. **Ложные негативы:** Generic слова удалены, но модель часто использует их
3. **Непредсказуемость:** Одинаковые кейсы дают разные результаты между запусками

## Что нужно исправить (в порядке приоритета)

### P0: Вернуть стабильность quality_gates

**Проблема:** Текущие CRITICAL_MARKERS слишком специфичны и пропускают реальные проблемы.

**Решение:** Гибридный подход:
```python
# Оставить специфичные фразы для TRUE critical (safety/legal/privacy)
TRUE_CRITICAL_PHRASES = (
    "safety issue", "legal compliance issue", "privacy leak", 
    "security exploit", "medical advice", "financial advice",
    "gdpr violation", "hipaa violation", ...
)

# Добавить generic слова но с контекстом
GENERIC_CRITICAL_WORDS = (
    "unsafe", "harmful", "illegal", "unlawful", "danger",
    "secret", "credential", "password", "token", "pii", ...
)

def _is_critical_text(value: Any) -> bool:
    text = _normalize_text(value)
    
    # Проверяем специфичные фразы
    if any(phrase in text for phrase in TRUE_CRITICAL_PHRASES):
        return True
    
    # Проверяем generic слова с контекстом
    # Исключаем false positives типа "recommendation to improve security"
    if any(word in text for word in GENERIC_CRITICAL_WORDS):
        # Проверяем что это не recommendation/suggestion
        if not any(marker in text for marker in ("recommend", "suggest", "improve", "better")):
            return True
    
    return False
```

### P1: Сделать answer_budget адаптивным

**Текущая проблема:** "Keep it concise" → 650 chars → убивает примеры

**Решение:**
```python
def derive_answer_budget(query: str, query_intake: dict | None = None) -> dict:
    # Детектим тип вопроса
    needs_examples = is_comparison or is_definition or 'example' in query
    
    if needs_examples:
        max_chars = 1000 if concise else 2200  # Больше для примеров
    else:
        max_chars = 650 if concise else 2200
```

### P2: Добавить детальное логирование

**Проблема:** Невозможно понять почему система приняла решение

**Решение:** Добавить trace для каждого quality gate decision:
```python
state.setdefault("quality_gate_trace", []).append({
    "gate": "critical_markers_check",
    "input_text": text,
    "matched_markers": [m for m in CRITICAL_MARKERS if m in text],
    "is_critical": result,
    "reason": "matched X markers" or "no matches",
    "timestamp": datetime.now().isoformat(),
})
```

### P3: Убрать hardcoded ответы

**Проблема:** Overfitting на датасет

**Решение:** Удалить `_enhance_direct_answer()`, улучшить промпт

## Тестовый план

### Тест 1: Откат quality_gates к стабильной версии
```bash
git show HEAD~2:Lib/quality_gates.py > Lib/quality_gates.py.backup
# Применить гибридный подход
python eval.py --dataset cmm_dataset_v2.csv --output eval_stable_gates --judge llm
```

**Ожидание:** V2-007 и V2-010 не должны падать

### Тест 2: Адаптивный answer_budget
```bash
# Изменить derive_answer_budget()
python eval.py --dataset cmm_dataset_v2.csv --output eval_adaptive_budget --judge llm
```

**Ожидание:** V2-003 должен победить

### Тест 3: Полный фикс
```bash
python eval.py --dataset cmm_dataset_v2.csv --output eval_complete_fix --judge llm
```

**Ожидание:** Avg delta > +1.0, стабильность на всех кейсах

## Критерии успеха

1. **Детерминированность:** Одинаковые кейсы дают одинаковые результаты (±0.5 delta)
2. **Avg delta > +1.0** на 20 кейсах
3. **FULL_CMM failures < 2** (сейчас 2-3)
4. **DIRECT качество восстановлено** (V2-003 CMM wins)
5. **Нет hardcoded ответов**

## Следующие шаги

1. Реализовать гибридный подход для CRITICAL_MARKERS
2. Добавить детальное логирование quality gates
3. Сделать answer_budget адаптивным
4. Запустить тесты
5. Если avg delta > +1.0 → коммитить
6. Если нет → итерировать на логике critical detection
