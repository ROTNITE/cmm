# Ответ на предложения: Этапы 5-6

**Дата:** 2026-05-06  
**Контекст:** После завершения 6 fixes + policy tests

## Этап 5: ID-based coverage ✅ Согласен, ВЫСОКИЙ приоритет

### Проблема
Сейчас plan_critic проверяет покрытие через text matching:
```python
def _item_covered(item: str, text: str) -> bool:
    if normalized in text:
        return True
    # Token matching...
```

Это дает ложные "не покрыто" когда:
- План использует синонимы
- План перефразирует
- План покрывает концептуально, но не текстуально

### Решение: ID-based coverage

**Deliberation brief:**
```python
{
  "must_address": [
    {"id": "MA-001", "text": "Consider search functionality", "severity": "medium", "type": "quality"},
    {"id": "MA-002", "text": "Privacy: user data storage", "severity": "high", "type": "privacy"}
  ]
}
```

**Planner возвращает:**
```python
{
  "steps": [...],
  "coverage": {
    "MA-001": "covered in step 2: Notion has built-in search",
    "MA-002": "covered in risk section: data stays in Notion cloud"
  },
  "covered_items": ["MA-001", "MA-002"]
}
```

**Plan critic проверяет:**
```python
def _entry_covered(entry: dict, plan: dict) -> bool:
    item_id = entry.get("id")
    if item_id and item_id in plan.get("covered_items", []):
        return True
    # Fallback to text matching
    return _item_covered(entry.get("text"), plan_text)
```

### Преимущества
1. **Детерминизм** - нет споров "покрыто или нет"
2. **Trace** - видно что именно покрыто и где
3. **Severity-aware** - можно блокировать только high severity
4. **Type-aware** - privacy/safety → NO_ANSWER_BLOCKER, quality → MUST_ADDRESS

### Реализация (2-3 часа)

**Файлы для изменения:**
1. `Lib/deliberation.py` - добавить ID generation
2. `Lib/planner.py` - добавить coverage dict в schema
3. `Lib/plan_critic.py` - использовать ID-based check
4. `tests/test_plan_critic.py` - добавить тесты

**Приоритет:** ВЫСОКИЙ - это решает проблему ложных "ignored_must_address"

---

## Этап 6: Нормализация eval ✅ Согласен, КРИТИЧНО

### Проблема
Сейчас невозможно сравнить runs:
- `eval_cmm_quality_fix_10`: mean delta +1.8
- `eval_cmm_quality_fix_10_final`: mean delta -1.5

Что изменилось? Код? Датасет? Judge? Model? Температура? Неизвестно.

### Решение: Version stamping + normalized metrics

**В каждый summary.json добавить:**
```json
{
  "version_info": {
    "code_hash": "abc123def456",
    "git_commit": "2731ae6aeb56b8c9967944e06eba47b42ae16ab0",
    "git_branch": "main",
    "git_dirty": false,
    "dataset_hash": "xyz789",
    "dataset_path": "cmm_dataset_v2.csv",
    "timestamp": "2026-05-06T17:50:00Z"
  },
  "config": {
    "model": "kr/claude-sonnet-4.5",
    "provider": "omniroute",
    "judge_model": "kr/claude-sonnet-4.5",
    "judge_prompt_version": "v2.1",
    "structured_output": true,
    "temperature_by_stage": {
      "query_intake": 0.3,
      "expert": 0.5,
      "planner": 0.3,
      "critic": 0.2,
      "judge": 0.0
    },
    "route_mode": "AUTO",
    "max_plan_iters": 2,
    "max_deliberation_rounds": 1,
    "max_meta_rechecks": 1
  },
  "metrics": {
    "technical_failure_rate": 0.3,
    "json_failure_rate_by_stage": {
      "query_intake": 0.0,
      "expert": 0.05,
      "planner": 0.1,
      "critic": 0.0
    },
    "empty_answer_rate": 0.3,
    "safety_block_rate": 0.0,
    "quality_best_effort_rate": 0.2,
    "judge_parse_failure_rate": 0.0,
    "mean_delta_excluding_technical_failures": 1.2,
    "mean_delta_including_technical_failures": -0.5,
    "router_accuracy": 0.9,
    "cmm_wins": 6,
    "baseline_wins": 4,
    "ties": 0
  }
}
```

### Преимущества
1. **Reproducibility** - можно воспроизвести точный run
2. **Regression detection** - видно что именно сломалось
3. **Fair comparison** - сравниваем только comparable runs
4. **Root cause analysis** - видно где именно провал

### Реализация (3-4 часа)

**Файлы для изменения:**
1. `cmm/eval.py` - добавить version stamping
2. `cmm/eval.py` - добавить normalized metrics
3. `cmm/eval.py` - добавить comparison tool
4. `tests/test_eval.py` - добавить тесты

**Новый инструмент:**
```bash
python -m cmm.compare_evals \
  --run1 eval_cmm_quality_fix_10 \
  --run2 eval_cmm_quality_fix_10_final \
  --output comparison.md
```

Выдаст:
```markdown
# Comparison: eval_cmm_quality_fix_10 vs eval_cmm_quality_fix_10_final

## Version Diff
- Code: abc123 → def456 (5 files changed)
- Git: 2731ae6 → 8f9a1b2
- Dataset: SAME
- Judge prompt: v2.0 → v2.1

## Metrics Diff
- technical_failure_rate: 0.1 → 0.3 ❌ REGRESSION
- empty_answer_rate: 0.1 → 0.3 ❌ REGRESSION
- mean_delta (excl failures): +1.8 → +1.2 ⚠️ DEGRADATION
- mean_delta (incl failures): +1.8 → -0.5 ❌ REGRESSION

## Root Cause
Technical failures increased from 1 to 3:
- V2-006: NEW failure (critical_plan_blockers)
- V2-007: NEW failure (critical_answer_moderation)
- V2-010: NEW failure (critical_plan_blockers)

All 3 failures are quality_gates related.
```

**Приоритет:** КРИТИЧНО - без этого невозможно инженерное улучшение

---

## Приоритизация

### Немедленно (сегодня)
1. ✅ **Тестировать 6 fixes** - eval на V2-006, V2-007, V2-010 (запущен)
2. ⏳ **Проверить результаты** - убедиться что пустые ответы исправлены

### Следующая неделя
3. **Этап 6: Version stamping** (3-4 часа) - КРИТИЧНО для измерения
4. **Этап 5: ID-based coverage** (2-3 часа) - ВЫСОКИЙ приоритет для стабильности

### Потом
5. **Frozen answers protocol** (2 часа) - для стабильного judge
6. **Полный eval на 20 кейсах** (1 час) - с version stamping

---

## Почему именно такой порядок?

**1. Fixes сначала** - без них система падает с пустыми ответами

**2. Version stamping второе** - без него мы не знаем что измеряем

**3. ID-based coverage третье** - это улучшение, не критический fix

**4. Frozen answers четвертое** - это про стабильность измерения, не про исправление системы

---

## Ожидаемые результаты после всех этапов

**Технические метрики:**
- `technical_failure_rate: 0.0` (было 0.3)
- `empty_answer_rate: 0.0` (было 0.3)
- `json_failure_rate: <0.05` (было 0.1-0.2)

**Качественные метрики:**
- `mean_delta_excluding_failures: +1.5` (было +1.2)
- `router_accuracy: 0.95` (было 0.9)
- `cmm_wins: 12-14/20` (было 6-8/10)

**Стабильность:**
- `judge_agreement: 0.8+` (новая метрика)
- `version_reproducibility: 100%` (новая метрика)

---

**Статус:** Согласен с обоими этапами. Приоритет: Version stamping → ID-based coverage.
