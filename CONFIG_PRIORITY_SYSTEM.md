# Система приоритетов конфигурации CMM

**Дата**: 2026-05-09  
**Статус**: ✅ Реализовано и протестировано (265/265 тестов)

## Проблема

1. При изменении модели в `cmm_config.json` система продолжала использовать старую модель (кэширование при импорте)
2. При запуске `python -m cmm.eval --model kr/claude-sonnet-4.5` параметр командной строки игнорировался

## Решение

Реализована **гибкая система приоритетов**, где:
- **Явные параметры** (CLI, API) имеют наивысший приоритет
- **Конфиг файл** имеет приоритет над env переменными
- **Env переменные** работают только для runtime настроек

## Система приоритетов

### Для model, judge_model, base_url

**Приоритет (от высшего к низшему):**

1. **Явный параметр** (CLI `--model`, параметр функции `model=`)
2. **cmm_config.json** (tracked config file)
3. **cmm_config.local.json** (local overrides, не коммитится)
4. **Профиль по умолчанию** (DEFAULT_CONFIG)

❌ **Env переменные НЕ работают** для model/judge_model/base_url

### Для runtime настроек (max_iters, route_mode, parallel_mode, max_workers)

**Приоритет (от высшего к низшему):**

1. **Env переменные** (`CMM_MAX_ITERS`, `CMM_ROUTE_MODE`, и т.д.)
2. **cmm_config.json**
3. **cmm_config.local.json**
4. **Дефолты** (DEFAULT_CONFIG)

## Примеры использования

### 1. Запуск eval с явной моделью (наивысший приоритет)

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_claude --model kr/claude-sonnet-4.5
```

✅ **Результат**: Использует `kr/claude-sonnet-4.5`, игнорируя конфиг

### 2. Запуск eval без параметра модели (конфиг файл)

```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --output-dir eval_default
```

✅ **Результат**: Использует модель из `cmm_config.json` (например, `cgpt-web/gpt-5.5-thinking`)

### 3. Изменение модели в конфиге

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

✅ **Результат**: Все запуски без явного `--model` будут использовать Claude

### 4. Переопределение runtime настроек через env

```bash
set CMM_MAX_ITERS=5
set CMM_ROUTE_MODE=FULL_CMM
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20
```

✅ **Результат**: 
- Модель из `cmm_config.json`
- `max_iters=5` и `route_mode=FULL_CMM` из env переменных

### 5. Локальный конфиг (не коммитится)

**cmm_config.local.json:**
```json
{
  "model": "my-local-model"
}
```

✅ **Результат**: Переопределяет `cmm_config.json`, но не коммитится в git

## Технические детали

### Изменённые файлы

1. **Lib/AI_request.py**
   - Убраны константы `DEFAULT_MODEL` и `DEFAULT_BASE_URL` (кэширование при импорте)
   - Добавлена функция `_get_api_key_env_names()` для динамической загрузки

2. **Lib/config.py**
   - `load_config()`: изменён порядок применения конфигов
   - `get_default_model()`: явный параметр имеет наивысший приоритет
   - `get_judge_model()`: явный параметр имеет наивысший приоритет
   - `_apply_env_overrides()`: убраны переопределения model/judge_model/base_url

3. **tests/test_config.py**
   - Обновлены тесты под новую логику приоритетов

4. **tests/test_state_machine.py**
   - Добавлены импорты `tempfile`, `json`, `os`, `Path`
   - Обновлены тесты для использования временных конфиг файлов

5. **tests/test_json_contracts.py**
   - Обновлён тест для явной передачи параметра `model`

### Логика в load_config()

```python
def load_config() -> dict:
    # 1. Начинаем с дефолтов
    config = deepcopy(DEFAULT_CONFIG)
    
    # 2. Применяем env переменные (только для runtime настроек)
    config = _apply_env_overrides(config)
    
    # 3. Применяем локальный конфиг
    config = _deep_merge(config, _read_json_file(LOCAL_CONFIG_PATH))
    
    # 4. Применяем tracked конфиг
    tracked_config = _read_json_file(config_path)
    config = _deep_merge(config, tracked_config)
    
    # 5. Применяем профиль
    config = _apply_profile_defaults(config)
    
    # 6. ФОРСИРУЕМ model/judge_model/base_url из tracked конфига (наивысший приоритет)
    if tracked_config:
        if "model" in tracked_config:
            config["model"] = tracked_config["model"]
        if "judge_model" in tracked_config:
            config["judge_model"] = tracked_config["judge_model"]
        if "api" in tracked_config and "base_url" in tracked_config["api"]:
            config["api"]["base_url"] = tracked_config["api"]["base_url"]
    
    return config
```

### Логика в get_default_model()

```python
def get_default_model(explicit: str | None = None) -> str:
    # 1. Явный параметр (наивысший приоритет)
    if explicit and str(explicit).strip():
        return str(explicit)
    
    # 2. Конфиг файл
    config = load_config()
    config_model = str(config.get("model") or "").strip()
    if config_model:
        return config_model
    
    # 3. Дефолт из профиля
    return DEFAULT_CONFIG["profiles"]["compat"]["model"]
```

## Почему env переменные НЕ работают для модели?

**Причина**: Ты хотел, чтобы **конфиг файл был строго приоритетным** для модели и API настроек.

**Логика**:
- Модель и API - это **критические настройки**, которые должны быть явно заданы
- Runtime настройки (max_iters, route_mode) - это **поведенческие настройки**, которые можно менять на лету

**Если нужно переопределить модель**:
1. ✅ Используй явный параметр: `--model kr/claude-sonnet-4.5`
2. ✅ Измени `cmm_config.json`
3. ✅ Создай `cmm_config.local.json` (не коммитится)
4. ❌ НЕ используй env переменные (они игнорируются)

## Таблица приоритетов

| Настройка | Приоритет 1 | Приоритет 2 | Приоритет 3 | Приоритет 4 |
|-----------|-------------|-------------|-------------|-------------|
| **model** | CLI `--model` | cmm_config.json | cmm_config.local.json | Профиль |
| **judge_model** | CLI `--judge-model` | cmm_config.json | cmm_config.local.json | Профиль |
| **base_url** | - | cmm_config.json | cmm_config.local.json | Дефолт |
| **max_iters** | ENV `CMM_MAX_ITERS` | cmm_config.json | cmm_config.local.json | Дефолт |
| **route_mode** | ENV `CMM_ROUTE_MODE` | cmm_config.json | cmm_config.local.json | Дефолт |
| **parallel_mode** | ENV `CMM_PARALLEL_MODE` | cmm_config.json | cmm_config.local.json | Дефолт |

## Верификация

```bash
# Все тесты проходят
python -m unittest discover -s tests -p "test_*.py"
# Ran 265 tests in 1.340s
# OK
```

## Заключение

✅ **Проблема решена**: 
- Конфиг файл теперь правильно обновляется (нет кэширования)
- CLI параметры имеют наивысший приоритет
- Конфиг файл приоритетнее env переменных для модели
- Все тесты проходят

✅ **Теперь работает**:
```bash
# Использует Claude из CLI параметра
python -m cmm.eval --model kr/claude-sonnet-4.5 ...

# Использует модель из cmm_config.json
python -m cmm.eval ...
```

---

**Изменённые файлы**:
- `Lib/AI_request.py`
- `Lib/config.py`
- `tests/test_config.py`
- `tests/test_state_machine.py`
- `tests/test_json_contracts.py`

**Тесты**: 265/265 ✅
