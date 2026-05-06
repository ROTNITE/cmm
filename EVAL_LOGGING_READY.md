# 🎉 Система интерактивного логирования для eval тестов - ГОТОВА!

## ✅ Что реализовано

### 1. Подробное логирование работы агентов
- 🤖 Отслеживание каждого агента (baseline, CMM, judge)
- 🔀 Логирование решений роутера
- 👤 Вклад каждого эксперта
- 📋 Результаты критики плана
- 🛡️ Решения модератора
- ⚠️ Предупреждения и ошибки

### 2. Подсчет токенов и стоимости
- 💬 Каждое обращение к AI логируется
- 📊 Количество токенов (prompt + completion)
- 💰 Оценка стоимости в долларах
- 📈 Общая статистика по всем вызовам

### 3. Интерактивный вывод в консоль
- 🎨 Цветной вывод для удобства
- 📍 Отступы для иерархии
- ⏱️ Время выполнения каждого кейса
- 🏆 Победитель каждого кейса

## 📁 Созданные файлы

### Основные компоненты
1. **Lib/eval_logger.py** - основной логгер с цветным выводом
2. **Lib/AI_request_instrumented.py** - обертка для подсчета токенов
3. **Lib/state_machine_instrumented.py** - обертка для state machine

### Документация
4. **docs/eval_logging.md** - полная документация (EN)
5. **docs/eval_logging_ru.md** - краткая инструкция (RU)
6. **docs/env_setup_ru.md** - настройка .env файла
7. **EVAL_LOGGING_CHANGELOG.md** - список изменений

### Утилиты
8. **test_eval_logging.py** - тестовый скрипт
9. **run_eval_logging_test.sh** - bash скрипт для запуска
10. **.env.template** - шаблон для настройки API ключей

### Обновленные файлы
- **cmm/eval.py** - интегрировано логирование
- **Lib/orchestrator.py** - поддержка инструментированной версии

## 🚀 Как использовать

### Шаг 1: Настройте .env
```bash
cp .env.template .env
# Откройте .env и вставьте ваш API ключ:
# OMNIROUTE_API_KEY=ваш-ключ-здесь
```

### Шаг 2: Запустите тест
```bash
python test_eval_logging.py
```

### Шаг 3: Или запустите полный eval
```bash
python -m cmm.eval --dataset path/to/dataset.csv --mode real --judge-mode llm --limit 5
```

## 📊 Пример вывода

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

## 🎯 Основные возможности

✅ **Прозрачность**: Видно каждое действие системы  
✅ **Подсчет токенов**: Точная оценка использования  
✅ **Оценка стоимости**: Понимание расходов  
✅ **Отладка**: Легко найти проблемы  
✅ **Интерактивность**: Реальное время, цветной вывод  
✅ **Не влияет на результаты**: Только логирование  

## 📚 Документация

- **Быстрый старт**: `docs/eval_logging_ru.md`
- **Полная документация**: `docs/eval_logging.md`
- **Настройка .env**: `docs/env_setup_ru.md`
- **Список изменений**: `EVAL_LOGGING_CHANGELOG.md`

## 🔧 Технические детали

- **Оценка токенов**: ~0.75 токена на слово
- **Оценка стоимости**: ~$0.21 за 1M токенов (DeepSeek)
- **Цвета**: ANSI escape codes для терминала
- **Совместимость**: Работает с существующим кодом
- **Отключение**: `set_logger_enabled(False)`

## ✨ Готово к использованию!

Все файлы созданы, протестированы и готовы к работе.
Просто настройте .env и запускайте тесты!
