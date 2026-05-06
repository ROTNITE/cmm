# CMM System Improvements Summary

## 🎯 Цель
Улучшить качество Collective Meta-Moderation системы для достижения стабильных побед над baseline в judge тестах.

## 📊 Результаты

### До исправлений
- **Judge не работал** - все результаты были TIE из-за ошибки API
- Проблема: использовался дефолтный `--judge-model "deepseek-chat"`, которого нет в локальном прокси

### После исправлений (4 кейса)
- **CMM wins: 3** (75%)
- **Ties: 1** (25%)
- **Baseline wins: 0** (0%)

## 🔧 Ключевые исправления

### 1. Judge теперь работает
**Проблема:** Judge использовал модель "deepseek-chat", которой нет в локальном прокси
**Решение:** Нужно указывать `--judge-model "kr/claude-sonnet-4.5"`

```bash
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --limit 10 \
  --mode real \
  --judge-mode llm \
  --model "kr/claude-sonnet-4.5" \
  --judge-model "kr/claude-sonnet-4.5"
```

### 2. Query intake извлекает brevity constraints
**Проблема:** Query intake игнорировал слова "кратко", "briefly" из самого вопроса
**Файл:** `Lib/query_intake.py:307`

**Было:**
```python
"- constraints: ONLY extract explicitly stated constraints from the query. Do NOT extract words from the question itself (e.g., if query is \"Briefly explain X\", do NOT add \"Briefly\" as a constraint)."
```

**Стало:**
```python
"- constraints: Extract ALL constraints including brevity/length requirements from the query itself (\"briefly\", \"кратко\", \"in 5 sentences\", \"short answer\") AND explicitly stated constraints. These are critical formatting requirements."
```

### 3. Direct answer строго соблюдает brevity
**Проблема:** Direct answer слабо соблюдал brevity constraints, писал слишком длинные ответы
**Файл:** `Lib/direct_answer.py:89`

**Было:**
```python
"- Respect any formatting constraints (brevity, sentence limits, etc.)"
```

**Стало:**
```python
"- STRICTLY respect brevity constraints (\"кратко\", \"briefly\", \"short\", sentence limits): when brevity is requested, prioritize conciseness over additional examples or details
- When brevity is requested: use 1 focused example instead of multiple, avoid redundant explanations, get to the point quickly"
```

## ❌ Провалившиеся стратегии

### Попытка 1: "Все через LIGHT_CMM"
**Идея:** Отправлять все запросы через LIGHT_CMM вместо DIRECT, чтобы использовать коллективное мышление

**Результат:** 
- CMM wins: 0
- Baseline wins: 2
- Ties: 1
- mean_cmm_overall: 3.0 (катастрофа!)

**Проблема:** LIGHT_CMM слишком строгий для простых вопросов, падает с failures:
- answer_moderation_rejected
- plan_needs_revision_after_max_iters
- critical_plan_blockers

**Вывод:** DIRECT режим работает хорошо для простых definition questions. Не нужно усложнять.

## 🐛 Найденные баги (не исправлены)

### 1. LIGHT_CMM падает с critical_answer_moderation_issues
**Проблема:** Когда answer_moderator возвращает REVISE, система переходит в FAILED и возвращает пустой ответ вместо попытки улучшить ответ.

**Файл:** `Lib/state_machine.py:1612-1622`

**Эффект:** V2-004 упал с пустым ответом (0.0 score) в одном из тестов

**Решение:** Нужно изменить логику, чтобы REVISE запускал улучшение ответа, а не блокировал его.

## 📈 Метрики улучшения

### Brevity compliance
- **До:** CMM писал 793 chars vs Baseline 591 chars (нарушение "кратко")
- **После:** CMM соблюдает brevity, получает 10.0 vs Baseline 9.0

### Judge scores
- **До исправлений:** CMM 8.0, Baseline 10.0 (проигрыш из-за длины)
- **После исправлений:** CMM 10.0, Baseline 9.0 (победа благодаря качеству + brevity)

### Win rate
- **До:** Невозможно измерить (judge не работал)
- **После:** 75% win rate (3 wins из 4 кейсов)

## 🎓 Уроки

1. **Простота работает** - DIRECT режим эффективен для простых вопросов, не нужно усложнять
2. **Constraints критичны** - соблюдение brevity constraints важнее добавления деталей
3. **Judge должен работать** - без работающего judge невозможно измерить качество
4. **LIGHT_CMM нужен для сложных задач** - не для всех запросов подряд

## 🚀 Следующие шаги

1. **Исправить LIGHT_CMM failures** - убрать избыточную строгость модерации
2. **Протестировать на большем датасете** - 20-30 кейсов для статистической значимости
3. **Оптимизировать token usage** - сейчас CMM использует больше токенов
4. **Улучшить LIGHT_CMM для средних задач** - сейчас он слишком строгий

## 📝 Команда для запуска eval

```bash
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --limit 10 \
  --mode real \
  --judge-mode llm \
  --model "kr/claude-sonnet-4.5" \
  --judge-model "kr/claude-sonnet-4.5" \
  --output-dir eval_results
```

## ✅ Итог

Система CMM теперь работает и показывает **75% win rate** благодаря:
1. Работающему judge
2. Правильному извлечению brevity constraints
3. Строгому соблюдению этих constraints в ответах

Основная проблема решена. Дальнейшие улучшения - это оптимизация и исправление edge cases.
