# JSON Hardening Fix - 2026-05-06

## Проблема

Real eval на `cmm_dataset_v1.csv` (case CMM-001) показал катастрофический сбой:
- **0/10 валидных экспертных вкладов** (все ушли в fallback)
- **Planner**: fallback mode
- **Plan critique**: 3x needs_revision
- **Final state**: FAILED
- **CMM answer**: пустой (0 chars)

Причина: DeepSeek не справился с JSON-контрактами экспертов при реальных вызовах.

## Реализованные фиксы

### 1. Экспертный слой (Lib/expert_agent.py)

**Было:**
- insights: 3-7, risks: 2-6, questions: 2-6, recommendations: 3-7
- tokens: 350
- temp: 0.25
- Мягкие промпты
- Технические ошибки попадали в `expert_risks`

**Стало:**
- **Фиксированные количества**: insights=3, risks=2, questions=2, recommendations=3
- **Ограничение длины**: max 120 chars per item
- **tokens: 500** (↑43%)
- **temp: 0.2** (↓ для стабильности)
- **CRITICAL markers** в промптах
- **Чистый fallback**: пустые массивы, технические ошибки только в `parse_warnings`

### 2. JSON Retry (Lib/json_retry.py)

**Добавлено:**
- `_strip_markdown_json()`: агрессивная очистка от ```json блоков
- Автоматическое извлечение JSON между первым `{` и последним `}`
- Более строгие repair промпты с нумерованными требованиями
- Показ только первых 1000 chars failed output (было 4000)

### 3. Планировщик (Lib/plan_development.py)

**Изменения:**
- quick: 300 → 400 tokens
- detailed: 600 → 800 tokens (↑33%)
- comprehensive: 1000 → 1200 tokens
- temp: 0.5 → 0.4 для detailed
- CRITICAL markers в system prompt
- Акцент на закрытие всех скобок

### 4. State Machine (Lib/state_machine.py)

**Degraded Mode:**
```python
if valid_contributions == 0 and fallback_contributions >= 5:
    state["expert_panel_degraded"] = True
    state["cmm_mode"] = f"{original_mode}_DEGRADED"
    state["warnings"].append("expert_panel_catastrophic_json_failure")
```

Теперь система явно помечает деградированный режим вместо молчаливого продолжения.

### 5. Тесты (tests/test_expert_agent.py)

Обновлен тест для нового поведения fallback:
- `risks: []` вместо `["invalid_json_from_model"]`
- Проверка пустых insights/recommendations/questions

## Результаты

✅ **218/218 тестов проходят**
✅ **Коммит создан**: `4a01c1f`
✅ **Backward compatibility**: старые вызовы работают

## Ожидаемые улучшения

1. **Выше JSON success rate**: фиксированные короткие массивы легче парсить
2. **Меньше token overflow**: 500 tokens достаточно для 3+2+2+3 коротких строк
3. **Чище deliberation context**: технические ошибки не попадают в `must_address`
4. **Лучшая observability**: degraded mode явно виден в trace

## Следующие шаги

### Немедленно:

```bash
# Тестовый прогон на одном кейсе
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 1 --mode real --judge-mode none --output-dir eval_real_hardened_1
```

**Проверить в results.json:**
- `expert_valid_contributions > 0`
- `expert_invalid_json_contributions < 5`
- `planner_raw_format == "json"`
- `cmm_final_state == "FINALIZE"`
- `answer_chars > 0`

### Если успешно:

```bash
# Прогон на 5 кейсах
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 5 --mode real --judge-mode none --output-dir eval_real_hardened_5
```

### Если всё ещё падает:

**Дополнительные меры:**
1. Снизить temp до 0.1 для экспертов
2. Увеличить tokens до 600
3. Добавить примеры валидного JSON в system prompt
4. Рассмотреть переход на structured output API (если доступно)

### Калибровка router:

После успешного прогона на v2 dataset:
```bash
python tools/analyze_eval_routing.py --input eval_real_hardened_5/results.csv --output eval_real_hardened_5/routing_analysis.csv
```

Проверить `router_mode_match` и скорректировать пороги в `Lib/router.py`.

## Риски и ограничения

⚠️ **Меньше контента**: 3+2+2+3 вместо 7+6+6+7 = меньше экспертного вклада
- Компенсация: более качественные короткие рекомендации лучше, чем пустой fallback

⚠️ **Всё ещё эвристики**: нет гарантии 100% JSON success rate
- Мониторинг: `json_health` в trace покажет реальную картину

⚠️ **DeepSeek-специфично**: другие модели могут вести себя иначе
- Решение: параметризовать контракты по модели в будущем

## Метрики успеха

**Минимальный порог для продолжения eval:**
- ≥70% expert contributions valid (7/10)
- ≥80% planner JSON success
- ≥50% cases reach FINALIZE

**Целевой порог для production-ready:**
- ≥90% expert contributions valid
- ≥95% planner JSON success
- ≥80% cases reach FINALIZE (с учетом legitimate quality gate blocks)

## Changelog

- 2026-05-06 02:14 UTC: Initial JSON hardening implementation
- Commit: `4a01c1f`
- Tests: 218/218 ✅
- Ready for real eval testing
