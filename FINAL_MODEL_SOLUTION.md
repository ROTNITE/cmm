# Финальное решение: Единая точка управления моделью

**Дата**: 2026-05-09  
**Статус**: ✅ РЕШЕНО - Все 266 тестов проходят

## Проблема

При запуске:
```bash
python -m cmm.eval --model kr/claude-sonnet-4.5 --judge-mode llm
```

Результат был:
- CMM и baseline: `kr/claude-sonnet-4.5` ✅
- Judge: `cgpt-web/gpt-5.5-thinking` ❌ (из конфига)

**Причина**: `--judge-model` не был указан, поэтому взялся из `cmm_config.json`

## Решение

Добавлена логика в `cmm/eval.py`: **если `--model` указан, но `--judge-model` нет, то judge использует ту же модель**.

### Изменение в cmm/eval.py

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate CMM against a baseline.")
    parser.add_argument("--dataset", required=True, help="Path to cmm_dataset_v1.csv")
    parser.add_argument("--limit", type=int, default=None, help="Optional case limit")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock", help="Evaluation mode")
    parser.add_argument("--judge-mode", choices=["none", "llm"], default="none", help="Judge mode for real eval")
    parser.add_argument("--judge-model", default=None, help="Model for --judge-mode llm. If not specified, uses --model value.")
    parser.add_argument("--model", default=None, help="Model for CMM and baseline. Defaults to config.")
    parser.add_argument("--output-dir", default="eval_results", help="Directory for CSV/JSON outputs")
    args = parser.parse_args(argv)

    # If --model is specified but --judge-model is not, use the same model for judge
    judge_model = args.judge_model if args.judge_model else args.model

    result = run_eval(
        dataset_path=args.dataset,
        limit=args.limit,
        mode=args.mode,
        output_dir=args.output_dir,
        judge_mode=args.judge_mode,
        judge_model=judge_model,  # <-- Теперь использует --model если --judge-model не указан
        model=args.model,
    )
```

## Теперь работает правильно

### Вариант 1: Одна модель для всего (рекомендуется)

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_claude --model kr/claude-sonnet-4.5
```

✅ **Результат**:
- CMM: `kr/claude-sonnet-4.5`
- Baseline: `kr/claude-sonnet-4.5`
- Judge: `kr/claude-sonnet-4.5` (автоматически)

### Вариант 2: Разные модели для CMM и Judge

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_mixed --model kr/claude-sonnet-4.5 --judge-model gpt-4o
```

✅ **Результат**:
- CMM: `kr/claude-sonnet-4.5`
- Baseline: `kr/claude-sonnet-4.5`
- Judge: `gpt-4o`

### Вариант 3: Модели из конфига (без параметров)

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_default
```

✅ **Результат**:
- CMM: из `cmm_config.json` → `model`
- Baseline: из `cmm_config.json` → `model`
- Judge: из `cmm_config.json` → `judge_model`

## Полная система приоритетов

### Для model (CMM и baseline)

1. **CLI `--model`** (наивысший приоритет)
2. **cmm_config.json** → `model`
3. **cmm_config.local.json** → `model`
4. **Профиль по умолчанию**

### Для judge_model

1. **CLI `--judge-model`** (наивысший приоритет)
2. **CLI `--model`** (если `--judge-model` не указан) ⭐ **НОВОЕ**
3. **cmm_config.json** → `judge_model`
4. **cmm_config.json** → `model` (fallback)
5. **cmm_config.local.json**
6. **Профиль по умолчанию**

## Примеры использования

### Тестирование на Claude

```bash
# Всё на Claude
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_claude --model kr/claude-sonnet-4.5

# Claude для CMM, GPT для judge
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_mixed --model kr/claude-sonnet-4.5 --judge-model gpt-4o
```

### Тестирование на GPT

```bash
# Всё на GPT
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_gpt --model gpt-4o
```

### Использование конфига

**cmm_config.json:**
```json
{
  "model": "kr/claude-sonnet-4.5",
  "judge_model": "kr/claude-sonnet-4.5",
  "api": {
    "base_url": "http://localhost:20128/v1"
  }
}
```

```bash
# Использует модели из конфига
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_default
```

## Все исправления в одном месте

### 1. Убрано кэширование при импорте (Lib/AI_request.py)

```python
# БЫЛО (кэшировалось при импорте):
DEFAULT_MODEL = get_default_model()
DEFAULT_BASE_URL = get_base_url()

# СТАЛО (динамическая загрузка):
# Константы убраны, используются функции напрямую
```

### 2. CLI параметр имеет наивысший приоритет (Lib/config.py)

```python
def get_default_model(explicit: str | None = None) -> str:
    # 1. Явный параметр (CLI) - наивысший приоритет
    if explicit and str(explicit).strip():
        return str(explicit)
    
    # 2. Конфиг файл
    config = load_config()
    config_model = str(config.get("model") or "").strip()
    if config_model:
        return config_model
    
    # 3. Дефолт
    return DEFAULT_CONFIG["profiles"]["compat"]["model"]
```

### 3. Judge использует ту же модель, если не указан отдельно (cmm/eval.py)

```python
# If --model is specified but --judge-model is not, use the same model for judge
judge_model = args.judge_model if args.judge_model else args.model
```

## Верификация

```bash
python -m unittest discover -s tests -p "test_*.py"
# Ran 266 tests in 1.415s
# OK ✅
```

## Заключение

✅ **Проблема полностью решена**:
- Одна команда `--model` управляет всеми моделями (CMM, baseline, judge)
- Можно переопределить judge отдельно через `--judge-model`
- Конфиг файл работает как fallback
- Нет кэширования, нет костылей
- Все 266 тестов проходят

✅ **Теперь команда работает как ожидается**:
```bash
python -m cmm.eval --model kr/claude-sonnet-4.5 --judge-mode llm ...
# CMM: kr/claude-sonnet-4.5
# Baseline: kr/claude-sonnet-4.5
# Judge: kr/claude-sonnet-4.5 ✅
```

---

**Изменённые файлы**:
1. `Lib/AI_request.py` - убрано кэширование
2. `Lib/config.py` - CLI приоритет выше конфига
3. `cmm/eval.py` - judge использует --model если --judge-model не указан
4. `tests/test_*.py` - обновлены тесты

**Тесты**: 266/266 ✅
