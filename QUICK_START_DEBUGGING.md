# Быстрый старт: Отладка CMM оценки

## Что было исправлено

### 🎯 Проблема 1: Все тесты заканчиваются TIE
**Решение:** Увеличен порог с 0.5 до 1.0 + улучшен промпт судьи

### 🎯 Проблема 2: План никогда не принимается
**Решение:** Смягчена логика - теперь допускается до 3 minor blockers

### 🎯 Проблема 3: Нет видимости что происходит
**Решение:** Добавлено детальное логирование планов, критики, оценок

### 🎯 Проблема 4: Результаты теряются при прерывании
**Решение:** Инкрементальная запись после каждого теста

## Запуск теста

```bash
# Короткий тест для проверки
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 5 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"

# Полный тест
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"
```

## Что смотреть в консоли

### ✅ План принят (хорошо)
```
[P] Plan critique: ready
    Overall score: 7.5/10
    Scores:
      query_alignment: 8.0
      constraint_coverage: 7.5
      ...
```

### ⚠️ План требует ревизии (нормально, если 1-2 раза)
```
[P] Plan critique: needs_revision
    Overall score: 6.2/10
    Ignored must_address: 2
    Ignored risks: 3
    Feedback (3):
      - Cover deliberation_brief.must_address items.
```

### ❌ План отклонен после max_iters (плохо)
```
[!] Warning: plan_needs_revision_after_max_iters; proceeding_with_best_effort_plan
```

### 🏆 Судья выбрал победителя (хорошо)
```
[J] Judge evaluation:
    Baseline overall: 5.5/10
    CMM overall: 7.2/10
    Delta: +1.7
    Winner: CMM
```

### 😐 Судья выбрал TIE (плохо, если часто)
```
[J] Judge evaluation:
    Baseline overall: 6.0/10
    CMM overall: 6.3/10
    Delta: +0.3
    Winner: TIE
```

## Мониторинг прогресса во время теста

```bash
# В другом терминале
watch -n 5 cat eval_results/progress.json

# Или на Windows
while ($true) { cls; cat eval_results/progress.json; sleep 5 }
```

## Анализ результатов

### Проверить распределение победителей
```bash
# Linux/Mac
cat eval_results/results.csv | cut -d',' -f5 | sort | uniq -c

# Windows PowerShell
Import-Csv eval_results/results.csv | Group-Object winner | Select Name, Count
```

### Проверить статусы планов
```bash
# Сколько раз план принимался с первой попытки
grep "ready" eval_results/results.csv | wc -l

# Сколько раз были ревизии
grep "needs_revision" eval_results/results.csv | wc -l
```

## Ожидаемые результаты

### ✅ Хорошие показатели
- CMM wins: 30-50%
- Baseline wins: 20-30%
- Ties: 20-40%
- План принят с 1-2 попытки: 70-80%

### ⚠️ Требует внимания
- Ties > 60% → судья слишком консервативен
- План отклонен после max_iters > 20% → критик слишком строг
- CMM wins < 20% → CMM не дает преимущества

### ❌ Критические проблемы
- Ties = 100% → судья сломан
- План никогда не принимается → критик сломан
- Все тесты падают с ошибками → проблема с моделью/API

## Быстрая диагностика проблем

### Проблема: Судья всегда выбирает TIE
```python
# Проверить в eval.py
_TIE_DELTA = 1.0  # Должно быть 1.0, не 0.5
```

### Проблема: План никогда не принимается
```python
# Проверить в plan_critic.py функцию _status_from_critique
# Должна быть логика с len(blockers) <= 3
```

### Проблема: Нет логов в консоли
```python
# Проверить что импортирован enhanced_logger
from Lib.eval_logger_enhanced import get_enhanced_logger
enhanced_logger = get_enhanced_logger()
enhanced_logger.enabled = True
```

## Файлы для анализа

### Во время теста
- `eval_results/progress.json` - прогресс
- `eval_results/results_incremental.csv` - текущие результаты
- `eval_results/cases_incremental.jsonl` - детали кейсов

### После теста
- `eval_results/results.csv` - финальные результаты
- `eval_results/summary.json` - статистика
- `eval_results/cases.jsonl` - полные детали всех кейсов

## Полезные команды

### Найти кейсы где CMM выиграл
```bash
grep ",CMM," eval_results/results.csv
```

### Найти кейсы с критическими блокерами
```bash
grep "critical_blockers" eval_results/cases.jsonl
```

### Посчитать среднее время на кейс
```bash
# Из логов консоли
grep "Time:" | awk '{sum+=$2; count++} END {print sum/count}'
```

## Следующие шаги

1. ✅ Запустить короткий тест (5 кейсов)
2. ✅ Проверить что логи выводятся
3. ✅ Проверить что файлы создаются инкрементально
4. ✅ Запустить полный тест (20 кейсов)
5. ✅ Проанализировать результаты
6. ✅ Если нужно - подкрутить пороги

## Контакты для вопросов

См. полную документацию в `EVALUATION_IMPROVEMENTS.md`
