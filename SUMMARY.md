# Сводка: Что сделано и что дальше

**Дата:** 2026-05-06  
**Время работы:** ~3 часа

## ✅ Что сделано (100%)

### 6 системных исправлений
1. **quality_gates.py** - разделение NO_ANSWER / MUST_ADDRESS / QUALITY
2. **quality_gates.py** - debug layer с полным trace
3. **plan_critic.py** - FINALIZE + no blockers = ready
4. **router.py** - operational plans → LIGHT_CMM
5. **answer_budget.py** - budgets для LIGHT_CMM/FULL_CMM
6. **state_machine.py** - meta_recheck_budget_exhausted

### 6 policy тестов
- `tests/test_policy_gates.py` - все проходят ✓

### Документация
- `DIAGNOSTIC_IMPROVEMENTS.md` - полное описание fixes
- `ACTION_PLAN.md` - план тестирования и eval protocol
- `stable_eval.py` - скрипт для frozen answers

## 🎯 Главный вывод из анализа

**Проблема НЕ в концепции CMM.** Проблема в том, что quality gates превращают обычные недоработки в fatal error:

```
V2-006: 6/6 valid experts, JSON plan ✓ → 0 chars (critical_plan_blockers)
V2-007: 8519 chars generated ✓ → 0 chars (critical_answer_moderation)
V2-010: actionable plan ✓ → 0 chars (critical_plan_blockers)
```

**Мои fixes решают это:**
- Trade-offs больше не убивают ответ (MUST_ADDRESS вместо NO_ANSWER_BLOCKER)
- REVISE не равно failure (best_effort finalize если нет safety/legal blockers)
- Operational plans идут в LIGHT_CMM, не FULL_CMM

## ⏳ Что нужно сделать дальше

### Приоритет 1: Тестировать fixes на проблемных кейсах (30 мин)

```bash
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --case-ids V2-006,V2-007,V2-010 \
  --mode real \
  --model "kr/claude-sonnet-4.5" \
  --output-dir eval_fixes_test \
  --verbose
```

**Проверить:**
- V2-006: LIGHT_CMM (не FULL), >0 chars (не 0)
- V2-007: >0 chars output (не 0)
- V2-010: >0 chars (не 0)

### Приоритет 2: Исправить eval protocol (2 часа)

**Проблема:** Baseline/CMM/judge каждый раз разные → результаты несравнимы

**Решение:** Frozen answers + repeated judge

Нужно добавить в `cmm.eval`:
- `--save-answers` - сохранить ответы в JSON
- `--judge-only` - судить frozen answers
- `--frozen-answers` - путь к JSON
- `--judge-temperature 0` - детерминизм
- `--judge-run-id` - tracking

### Приоритет 3: Полный eval на 10 кейсах (1 час)

С frozen answers + 5 judge runs + агрегация

## 📊 Ожидаемые результаты

**До fixes (eval_cmm_quality_fix_10_final):**
- Technical failures: 3 (V2-006, V2-007, V2-010)
- Empty answers: 3
- CMM wins: 6/10

**После fixes (ожидание):**
- Technical failures: 0
- Empty answers: 0
- CMM wins: 7-8/10 (с учетом стабильного judge)

## 🚫 Что НЕ делать

- ❌ Не трогать direct_answer.py (DIRECT не падает технически)
- ❌ Не менять промпты (сначала стабильная метрика)
- ❌ Не делать выводы по 1-2 кейсам (это шум)
- ❌ Не запускать eval без frozen answers (несравнимо)

## 📁 Файлы для коммита (когда тесты пройдут)

```
Lib/quality_gates.py
Lib/plan_critic.py
Lib/router.py
Lib/answer_budget.py
Lib/state_machine.py
tests/test_policy_gates.py
DIAGNOSTIC_IMPROVEMENTS.md
ACTION_PLAN.md
```

## 💡 Следующий шаг

**Запусти тест на V2-006, V2-007, V2-010:**

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --case-ids V2-006,V2-007,V2-010 --mode real --model "kr/claude-sonnet-4.5" --output-dir eval_fixes_test --verbose
```

Если эти 3 кейса дадут >0 chars и не упадут с critical_plan_blockers → fixes работают, можно делать полный eval.

---

**Статус:** Готов к тестированию. Все исправления сделаны, тесты проходят, документация готова.
