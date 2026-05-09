# Инкрементальное логирование - Готово

**Дата:** 2026-05-08  
**Статус:** ✅ РЕАЛИЗОВАНО

---

## Что сделано

### Добавлено инкрементальное логирование в файл

Теперь логи каждого кейса записываются в файл **сразу после завершения** кейса, как и другие инкрементальные файлы.

**Файл:** `console_incremental.log` в папке результатов

---

## Как это работает

### 1. Логи накапливаются во время выполнения кейса

```python
class EnhancedEvalLogger:
    def __init__(self):
        self.case_logs = []  # Накапливаем логи текущего кейса
        self.log_file = None  # Путь к файлу

    def _print(self, message: str, level: int = 0):
        # Выводим в консоль
        print(full_message)
        # И сохраняем в case_logs
        if self.current_case:
            self.case_logs.append(full_message)
```

### 2. После каждого кейса логи записываются в файл

```python
# В eval.py после каждого кейса:
enhanced_logger.case_end(case_id, winner, time_seconds)
enhanced_logger.flush_case_logs()  # Записываем в файл
```

### 3. Файл обновляется инкрементально

```python
def flush_case_logs(self):
    with open(self.log_file, 'a', encoding='utf-8') as f:
        f.write('\n'.join(self.case_logs))
        f.write('\n\n')
```

---

## Пример содержимого файла

```
================================================================================
[*] CASE: V2-001
Query: Что такое коллективная метамодерация?
--------------------------------------------------------------------------------
[R] Router: DIRECT (complexity: low)

[J] Judge evaluation:
      Baseline overall: 8.00/10
      CMM overall: 9.00/10
      Delta: +1.00
      Winner: CMM
      Reason: Both answers meet the constraint...

[+] Winner: CMM
Time: 23.13s
================================================================================


================================================================================
[*] CASE: V2-002
Query: Кратко объясни разницу между метрикой и KPI.
--------------------------------------------------------------------------------
[R] Router: DIRECT (complexity: low)

[J] Judge evaluation:
      Baseline overall: 9.00/10
      CMM overall: 9.00/10
      Delta: +0.00
      Winner: CMM
      Reason: Both answers cover the rubric...

[+] Winner: CMM
Time: 23.38s
================================================================================
```

---

## Инкрементальные файлы

Теперь после каждого кейса обновляются:

1. ✅ `results_incremental.csv` - результаты
2. ✅ `cases_incremental.jsonl` - детали кейсов
3. ✅ `progress.json` - прогресс
4. ✅ `console_incremental.log` - логи консоли (НОВОЕ!)

---

## Преимущества

### Можно мониторить прогресс в реальном времени

```bash
# Смотреть логи в реальном времени
tail -f eval_results/run_final/console_incremental.log

# Или на Windows
Get-Content eval_results\run_final\console_incremental.log -Wait
```

### Логи не теряются при прерывании

Если тест прервется, все логи завершенных кейсов сохранены в файле.

### Кириллица отображается корректно

Файл записывается с `encoding='utf-8'`, поэтому кириллица читается нормально.

---

## Измененные файлы

### 1. `Lib/eval_logger_enhanced.py`

**Добавлено:**
- `self.case_logs = []` - накопление логов
- `self.log_file = None` - путь к файлу
- `set_log_file(path)` - установка пути
- `flush_case_logs()` - запись в файл
- Изменен `_print()` - добавляет в case_logs
- Изменен `case_start()` - очищает case_logs

### 2. `cmm/eval.py`

**Добавлено:**
- Установка log_file:
  ```python
  log_file_path = out_dir / "console_incremental.log"
  enhanced_logger.set_log_file(str(log_file_path))
  ```

- Вызов flush после каждого кейса:
  ```python
  enhanced_logger.case_end(case_id, winner, time_seconds)
  enhanced_logger.flush_case_logs()
  ```

---

## Использование

### Запуск теста

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"
```

### Мониторинг логов в реальном времени

```bash
# Linux/Mac
tail -f eval_results/console_incremental.log

# Windows PowerShell
Get-Content eval_results\console_incremental.log -Wait -Tail 50
```

### Чтение логов после завершения

```bash
cat eval_results/console_incremental.log
```

---

## Итог

✅ Логи записываются инкрементально
✅ Кириллица отображается корректно
✅ Можно мониторить в реальном времени
✅ Логи не теряются при прерывании

**Система полностью готова!**
