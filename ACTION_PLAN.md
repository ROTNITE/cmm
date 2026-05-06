# План действий: Исправление eval protocol + тестирование fixes

**Дата:** 2026-05-06  
**Статус:** ГОТОВ К ВЫПОЛНЕНИЮ

## Проблема

**Нестабильность измерения:** На одних и тех же кейсах результаты скачут от "2 CMM wins" до "0 wins, 2 ties" из-за:
1. Baseline каждый раз генерируется заново
2. CMM каждый раз генерируется заново
3. Judge каждый раз другой
4. На DIRECT кейсах разница микроскопическая → TIE/CMM/baseline плавает

**Реальная проблема (найдена в старых логах):**
- V2-006: 6/6 valid experts, JSON plan ok → **0 chars output** (critical_plan_blockers)
- V2-007: 8519 chars generated → **0 chars output** (critical_answer_moderation_issues)
- V2-010: actionable plan → **0 chars output** (critical_plan_blockers)

## Что уже исправлено (6 fixes)

✅ **1. Разделение классов блокеров** (quality_gates.py)
- NO_ANSWER_BLOCKER: safety/legal/privacy → блокирует
- MUST_ADDRESS_IN_ANSWER: trade-offs/risks → должны быть в ответе
- QUALITY_IMPROVEMENT: style → рекомендации

✅ **2. Debug-слой** (quality_gates.py)
- `create_quality_gate_debug()` показывает какое слово/правило создало blocker

✅ **3. Plan critic normalizer** (plan_critic.py)
- "ready for final answer" + no blockers → status = "ready"

✅ **4. Router operational plans** (router.py)
- "план запуска базы знаний" + "недорого" + "за месяц" → LIGHT_CMM

✅ **5. Answer budget для CMM** (answer_budget.py)
- LIGHT_CMM: 1200-2500 chars
- FULL_CMM: 2500-4500 chars

✅ **6. Переименование meta_recheck_limit** (state_machine.py)
- `meta_recheck_budget_exhausted` + "synthesizing with decision rules"

✅ **7. Policy tests** (tests/test_policy_gates.py)
- 6 тестов, все проходят

## Приоритет 1: Исправить eval protocol (КРИТИЧНО)

### Проблема
Сейчас каждый запуск eval:
1. Генерирует новый baseline
2. Генерирует новый CMM
3. Генерирует нового judge
→ Результаты несравнимы между запусками

### Решение: Frozen answers + repeated judge

**Шаг 1: Сгенерировать frozen answers один раз**
```bash
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --limit 10 \
  --mode real \
  --model "kr/claude-sonnet-4.5" \
  --output-dir eval_frozen_generation \
  --save-answers
```

**Шаг 2: Запустить judge 5 раз на frozen answers**
```bash
for i in {1..5}; do
  python -m cmm.eval \
    --judge-only \
    --frozen-answers eval_frozen_generation/answers.json \
    --judge-model "kr/claude-sonnet-4.5" \
    --judge-temperature 0 \
    --judge-run-id $i \
    --output-dir eval_frozen_judge_run_$i
done
```

**Шаг 3: Агрегировать результаты**
```bash
python aggregate_judge_results.py \
  --judge-runs eval_frozen_judge_run_* \
  --output eval_frozen_aggregated.csv
```

### Что нужно добавить в cmm.eval

1. **Флаг `--save-answers`** - сохранить baseline/CMM ответы в JSON
2. **Флаг `--judge-only`** - не генерировать ответы, только судить
3. **Флаг `--frozen-answers`** - путь к frozen answers JSON
4. **Флаг `--judge-temperature`** - температура для judge (0 для детерминизма)
5. **Флаг `--judge-run-id`** - ID прогона для tracking

### Новые поля в CSV

```csv
baseline_answer_hash,cmm_answer_hash,judge_run_id,judge_repeats,winner_majority,winner_margin,is_unstable_case
abc123,def456,1,5,CMM,0.6,False
abc123,def456,2,5,TIE,0.0,True
```

## Приоритет 2: Тестировать fixes на проблемных кейсах

### Кейсы для тестирования

**V2-006** (был: FULL_CMM, critical_plan_blockers, 0 chars)
- Ожидание: LIGHT_CMM, must_address items в ответе, >0 chars

**V2-007** (был: 8519 chars generated → 0 chars output)
- Ожидание: best_effort finalize, >0 chars output

**V2-010** (был: critical_plan_blockers, 0 chars)
- Ожидание: must_address items в ответе, >0 chars

### Команда для тестирования

```bash
# С новыми fixes
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --case-ids V2-006,V2-007,V2-010 \
  --mode real \
  --model "kr/claude-sonnet-4.5" \
  --output-dir eval_fixes_test \
  --verbose
```

### Что проверить в результатах

1. **V2-006:**
   - `actual_mode: LIGHT_CMM` (не FULL_CMM)
   - `cmm_answer_chars > 0` (не 0)
   - `cmm_warnings` не содержит `critical_plan_blockers`
   - `quality_gate_debug` показывает trade-offs в `must_address`, не `no_answer_blockers`

2. **V2-007:**
   - `cmm_answer_chars > 0` (не 0)
   - `answer_moderation_final_decision: ACCEPT` или `REVISE` с best_effort
   - `cmm_warnings` не содержит `critical_answer_moderation_issues`

3. **V2-010:**
   - `cmm_answer_chars > 0` (не 0)
   - `cmm_warnings` не содержит `critical_plan_blockers`
   - `quality_gate_debug` показывает что blockers классифицированы правильно

## Приоритет 3: Полный eval на 10 кейсах

После того как V2-006, V2-007, V2-010 пройдут:

```bash
# Генерация frozen answers
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --limit 10 \
  --mode real \
  --model "kr/claude-sonnet-4.5" \
  --output-dir eval_fixes_frozen \
  --save-answers

# Judge 5 раз
for i in {1..5}; do
  python -m cmm.eval \
    --judge-only \
    --frozen-answers eval_fixes_frozen/answers.json \
    --judge-model "kr/claude-sonnet-4.5" \
    --judge-temperature 0 \
    --judge-run-id $i \
    --output-dir eval_fixes_judge_$i
done

# Агрегация
python aggregate_judge_results.py \
  --judge-runs eval_fixes_judge_* \
  --output eval_fixes_stable.csv
```

### Ожидаемые результаты

**Технические метрики:**
- `technical_failures: 0` (было 3-4)
- `router_accuracy: 0.9+` (было 0.6-0.9)
- `empty_answer_count: 0` (было 3)

**Качественные метрики:**
- `mean_cmm_score: 7.5+` (было 5.5-8.7)
- `mean_baseline_score: 7.5+` (было 7.9-8.1)
- `cmm_wins: 6+` (было 5-8)
- `baseline_wins: ≤4` (было 2-5)

**Стабильность:**
- `unstable_cases: ≤2` (новая метрика)
- `judge_agreement: 0.8+` (новая метрика)

## Приоритет 4: Коммит если успешно

Если eval_fixes_stable показывает улучшение:

```bash
git add Lib/quality_gates.py Lib/plan_critic.py Lib/router.py Lib/answer_budget.py Lib/state_machine.py tests/test_policy_gates.py
git commit -m "Fix quality gates: separate blocker classes + debug layer + policy tests

- Separate NO_ANSWER_BLOCKER / MUST_ADDRESS / QUALITY_IMPROVEMENT
- Add create_quality_gate_debug() for explainable trace
- Fix plan_critic normalizer: FINALIZE + no blockers = ready
- Router: operational plans → LIGHT_CMM not FULL_CMM
- Add answer budget for LIGHT_CMM (1200-2500) and FULL_CMM (2500-4500)
- Rename meta_recheck_limit → meta_recheck_budget_exhausted
- Add 6 policy tests (all passing)

Fixes:
- V2-006: trade-offs no longer create critical_plan_blockers
- V2-007: answer_moderation REVISE allows best_effort finalize
- V2-010: actionable plans with must_address items can finalize

Tests: python -m unittest tests.test_policy_gates -v"
```

## Что НЕ делать

❌ **Не трогать direct_answer.py** - DIRECT кейсы не падают технически, они просто плавают из-за judge
❌ **Не менять промпты** - сначала нужна стабильная метрика
❌ **Не делать выводы по 1-2 кейсам** - это шум
❌ **Не запускать eval без frozen answers** - результаты несравнимы

## Следующие шаги

1. ✅ **Fixes готовы** - 6 исправлений + 6 тестов
2. ⏳ **Тестировать V2-006, V2-007, V2-010** - проверить что пустые ответы исправлены
3. ⏳ **Реализовать frozen answers protocol** - добавить флаги в cmm.eval
4. ⏳ **Полный eval на 10 кейсах** - с frozen answers + repeated judge
5. ⏳ **Коммит если успешно** - только после стабильных результатов

## Временная оценка

- Тестирование V2-006/007/010: **30 минут**
- Реализация frozen answers: **2 часа**
- Полный eval с агрегацией: **1 час**
- **Итого: ~3.5 часа**

---

**Главный вывод:** Концепция CMM не провалилась. Провалился слой "контроль качества как блокировка". Fixes готовы, теперь нужна стабильная метрика для проверки.
