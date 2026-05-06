# Система логирования для eval тестов

## Быстрый старт

Запустите eval тесты как обычно - логирование включится автоматически:

```bash
python -m cmm.eval --dataset eval_intake_fix_final/dataset.csv --limit 2 --mode real --judge-mode llm
```

Или используйте тестовый скрипт:

```bash
python test_eval_logging.py
```

## Что вы увидите

### Для каждого кейса:
- 🔍 Начало кейса с ID и запросом
- ▶ Стадии: BASELINE → CMM → JUDGE
- 💬 Каждое обращение к AI с количеством токенов
- 🏆 Победитель и время выполнения

### Для CMM стадии:
- 🔀 Решение роутера (DIRECT/LIGHT_CMM/FULL_CMM)
- 👤 Вклад каждого эксперта
- 📋 Результаты критики плана
- 🛡️ Решения модератора
- ⚠️ Предупреждения и ❌ ошибки

### В конце:
- 📊 Общая статистика
- Количество вызовов AI
- Общее количество токенов
- Оценка стоимости в долларах

## Пример вывода

```
================================================================================
🔍 CASE: CASE-1
Query: How to improve engagement?
================================================================================

▶ Stage: BASELINE
  💬 AI Call #1 [baseline]
    Model: deepseek-chat
    Tokens: 45 prompt + 320 completion = 365 total
    Running total: 365 tokens
  ✓ BASELINE complete

▶ Stage: CMM
  🔀 Router: LIGHT_CMM (complexity: medium)
  💬 AI Call #2 [router]
    Tokens: 120 prompt + 80 completion = 200 total
    Running total: 565 tokens
  👤 Expert: strategy_expert (strategy) - valid
  💬 AI Call #3 [expert_agent]
    Tokens: 250 prompt + 400 completion = 650 total
    Running total: 1215 tokens
  ✓ CMM complete

▶ Stage: JUDGE
  💬 AI Call #4 [judge]
    Tokens: 890 prompt + 150 completion = 1040 total
    Running total: 2255 tokens
  ✓ JUDGE complete

🏆 Winner: CMM
Time: 8.5s
================================================================================

📊 EVALUATION SUMMARY
Total AI calls: 4
Total tokens used: 2,255
Estimated cost: $0.0005
================================================================================
```

## Технические детали

### Созданные файлы:
- `Lib/eval_logger.py` - основной логгер
- `Lib/AI_request_instrumented.py` - обертка для отслеживания токенов
- `Lib/state_machine_instrumented.py` - обертка для state machine
- `cmm/eval.py` - обновлен для использования логирования

### Оценка токенов:
- ~0.75 токена на слово (приблизительно)
- Отдельно prompt и completion
- Общий счетчик для всего eval run

### Оценка стоимости:
- DeepSeek: ~$0.21 за 1M токенов (усредненно)
- Можно настроить в `Lib/eval_logger.py`

## Отключение

Если нужно отключить логирование:

```python
from Lib.eval_logger import set_logger_enabled
set_logger_enabled(False)
```

Или просто не используйте `mode="real"` - в mock режиме логирование не активно.
