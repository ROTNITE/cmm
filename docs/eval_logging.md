# Eval Logging System

Система подробного интерактивного логирования для judge тестов с отслеживанием работы агентов и использования токенов.

## Возможности

- 🔍 **Отслеживание кейсов**: Начало и конец каждого тестового кейса
- 🤖 **Логирование агентов**: Работа каждого агента (baseline, CMM, judge)
- 💬 **Подсчет токенов**: Каждое обращение к AI с количеством использованных токенов
- 🔀 **Router решения**: Режим работы и сложность запроса
- 👤 **Expert contributions**: Вклад каждого эксперта
- 📋 **Plan critique**: Результаты критики плана
- 🛡️ **Moderation**: Решения модератора
- ⚠️ **Warnings & Errors**: Предупреждения и ошибки в процессе
- 📊 **Итоговая статистика**: Общее количество вызовов AI и токенов, оценка стоимости

## Использование

### Автоматическое включение

Логирование автоматически включается при запуске `run_eval` в режиме `mode="real"`:

```python
from cmm.eval import run_eval

result = run_eval(
    dataset_path="path/to/dataset.csv",
    limit=5,
    mode="real",  # Логирование включено автоматически
    judge_mode="llm",
    output_dir="eval_results",
)
```

### Тестовый запуск

Используйте тестовый скрипт для проверки:

```bash
python test_eval_logging.py
```

### Пример вывода

```
================================================================================
🔍 CASE: CASE-1
Query: How to improve engagement in hybrid university?
================================================================================

▶ Stage: BASELINE
  💬 AI Call #1 [baseline]
    Model: deepseek-chat
    Tokens: 45 prompt + 320 completion = 365 total
    Running total: 365 tokens
  ✓ BASELINE complete

▶ Stage: CMM
  Starting CMM state machine (route_mode=AUTO)
  🔀 Router: LIGHT_CMM (complexity: medium)
    Reasoning: Query requires multiple perspectives...
  💬 AI Call #2 [router]
    Model: deepseek-chat
    Tokens: 120 prompt + 80 completion = 200 total
    Running total: 565 tokens
  👤 Expert: strategy_expert (strategy) - valid
  💬 AI Call #3 [expert_agent]
    Model: deepseek-chat
    Tokens: 250 prompt + 400 completion = 650 total
    Running total: 1215 tokens
  👤 Expert: user_experience (user) - valid
  💬 AI Call #4 [expert_agent]
    Model: deepseek-chat
    Tokens: 250 prompt + 380 completion = 630 total
    Running total: 1845 tokens
  📋 Plan critique: APPROVED
  🛡️ Moderation: APPROVED
  CMM completed with state: FINALIZE
  ✓ CMM complete

▶ Stage: JUDGE
  💬 AI Call #5 [judge]
    Model: deepseek-chat
    Tokens: 890 prompt + 150 completion = 1040 total
    Running total: 2885 tokens
  ✓ JUDGE complete

🏆 Winner: CMM
Time: 12.34s
================================================================================

================================================================================
📊 EVALUATION SUMMARY
Total AI calls: 5
Total tokens used: 2,885
Estimated cost: $0.0006
================================================================================
```

## Компоненты

### 1. `Lib/eval_logger.py`
Основной класс логгера с методами для различных типов событий.

### 2. `Lib/AI_request_instrumented.py`
Обертка над `AI_request.send_to_AI` с отслеживанием токенов.

### 3. `Lib/state_machine_instrumented.py`
Обертка над state machine для логирования переходов состояний.

### 4. `cmm/eval.py` (обновлен)
Интегрирует логирование в процесс evaluation.

## Оценка токенов

Система использует приблизительную оценку токенов:
- ~0.75 токена на слово для английского/русского текста
- Подсчитываются отдельно prompt и completion токены
- Ведется общий счетчик использованных токенов

## Оценка стоимости

По умолчанию используются примерные тарифы DeepSeek:
- ~$0.14 за 1M входных токенов
- ~$0.28 за 1M выходных токенов
- Средняя оценка: ~$0.21 за 1M токенов (при соотношении 50/50)

Вы можете настроить тарифы в `Lib/eval_logger.py` в методе `summary()`.

## Отключение логирования

Логирование можно отключить программно:

```python
from Lib.eval_logger import set_logger_enabled

set_logger_enabled(False)
```

## Цветовая схема

- 🔵 Синий: Стадии и router решения
- 🟢 Зеленый: Успешное завершение
- 🟡 Желтый: AI вызовы, предупреждения
- 🔴 Красный: Ошибки
- 🟣 Фиолетовый: Агенты
- 🔷 Голубой: Информация

## Примечания

- Оценка токенов приблизительная, для точного подсчета нужен доступ к API response
- Логирование не влияет на результаты evaluation
- Все логи выводятся в stdout с flush для интерактивности
