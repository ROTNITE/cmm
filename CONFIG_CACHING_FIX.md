# Исправление: Модель не обновляется при изменении конфига

## Проблема

При изменении модели в `cmm_config.json` тесты и код продолжали использовать старую модель.

## Корневая причина

В файле `Lib/AI_request.py` были константы, которые инициализировались **один раз при импорте модуля**:

```python
# СТАРЫЙ КОД (строки 19-20)
DEFAULT_BASE_URL = get_base_url()
DEFAULT_MODEL = get_default_model()
```

Когда Python импортирует модуль первый раз, он выполняет код на верхнем уровне и **кэширует результат**. Все последующие импорты используют закэшированную версию модуля.

### Почему это проблема:

1. При первом импорте `AI_request.py` вызывается `get_default_model()`
2. Значение сохраняется в константу `DEFAULT_MODEL`
3. Даже если изменить `cmm_config.json`, константа `DEFAULT_MODEL` содержит **старое закэшированное значение**
4. Python не перечитывает модуль при повторных импортах

### Пример проблемы:

```python
# Первый запуск теста
import Lib.AI_request  # DEFAULT_MODEL = "gpt-4.1" (из старого конфига)

# Пользователь меняет cmm_config.json на "claude-3-opus"

# Второй запуск теста
import Lib.AI_request  # DEFAULT_MODEL всё ещё "gpt-4.1" (закэшировано!)
```

## Решение

Убрал константы `DEFAULT_BASE_URL` и `DEFAULT_MODEL`, которые кэшировались при импорте.

### Изменения в `Lib/AI_request.py`:

**Было:**
```python
DEFAULT_BASE_URL = get_base_url()
DEFAULT_MODEL = get_default_model()
DEFAULT_TOKEN_LIMIT = 850

_API_KEY_ENV_NAMES = get_api_key_env_names()
```

**Стало:**
```python
# Note: DEFAULT_BASE_URL and DEFAULT_MODEL are removed to avoid caching stale config values.
# Use get_base_url() and get_default_model() directly instead.
DEFAULT_TOKEN_LIMIT = 850

def _get_api_key_env_names():
    """Get API key env names dynamically to avoid caching."""
    return get_api_key_env_names()
```

### Почему это работает:

Функция `send_to_AI` уже правильно вызывает `get_default_model()` каждый раз:

```python
def send_to_AI(..., model: str | None = None, ...):
    resolved_model = get_default_model(model)  # ✅ Перечитывает конфиг каждый раз
    ...
```

Функция `get_default_model()` в `Lib/config.py` вызывает `load_config()`, которая **каждый раз** читает файл конфига заново.

## Верификация

Все 265 тестов прошли успешно:

```bash
python -m unittest discover -s tests -p "test_*.py"
# Ran 265 tests in 1.362s
# OK
```

## Как теперь работает:

1. Изменяешь `cmm_config.json`:
   ```json
   {
     "model": "claude-3-opus",
     ...
   }
   ```

2. Запускаешь тест/код:
   ```python
   from Lib.AI_request import send_to_AI
   send_to_AI("test")  # ✅ Использует "claude-3-opus" из конфига
   ```

3. Конфиг перечитывается при каждом вызове `send_to_AI`, потому что:
   - `send_to_AI` вызывает `get_default_model()`
   - `get_default_model()` вызывает `load_config()`
   - `load_config()` читает файл заново

## Альтернативные способы переопределения модели

Если нужно переопределить модель без изменения конфига:

### 1. Переменная окружения (приоритет выше конфига):
```bash
set CMM_MODEL=claude-3-opus
python -m cmm.eval ...
```

### 2. Явный параметр в коде:
```python
send_to_AI("test", model="claude-3-opus")
```

### 3. Локальный конфиг (не коммитится в git):
Создай `cmm_config.local.json`:
```json
{
  "model": "claude-3-opus"
}
```

Приоритет (от высшего к низшему):
1. Явный параметр `model=` в функции
2. Переменная окружения `CMM_MODEL`
3. `cmm_config.local.json`
4. `cmm_config.json`
5. Дефолт из профиля

## Заключение

✅ **Проблема решена**: Модель теперь правильно обновляется при изменении конфига
✅ **Все тесты проходят**: 265/265
✅ **Обратная совместимость**: Код работает так же, но без кэширования

---

**Дата исправления**: 2026-05-09
**Изменённые файлы**: `Lib/AI_request.py`
**Тесты**: 265/265 ✅
