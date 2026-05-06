# 🎯 ГОТОВО! Инструкция для запуска

## Что сделано

✅ Создана система интерактивного логирования для eval тестов  
✅ Отслеживание работы каждого агента  
✅ Подсчет токенов для каждого обращения к AI  
✅ Оценка стоимости в долларах  
✅ Цветной интерактивный вывод в консоль  

## 📋 Что нужно сделать СЕЙЧАС

### 1. Настройте .env файл

Я создал шаблон `.env.template`. Вам нужно:

```bash
# Скопируйте шаблон
cp .env.template .env

# Откройте .env в любом редакторе
notepad .env
# или
code .env
```

**Вставьте ваш API ключ:**
```env
OMNIROUTE_API_KEY=ваш-ключ-здесь
```

Сохраните файл.

### 2. Запустите тест

```bash
python test_eval_logging.py
```

Вы увидите:
- 🔍 Каждый кейс с его ID и запросом
- 💬 Каждое обращение к AI с количеством токенов
- 🤖 Работу всех агентов
- 📊 Итоговую статистику: вызовы, токены, стоимость

## 📁 Структура файлов

```
cmm-main/
├── .env.template          ← Шаблон для вашего .env
├── .env                   ← СОЗДАЙТЕ ЭТОТ ФАЙЛ (не в git)
├── test_eval_logging.py   ← Тестовый скрипт
├── Lib/
│   ├── eval_logger.py                  ← Основной логгер
│   ├── AI_request_instrumented.py      ← Подсчет токенов
│   └── state_machine_instrumented.py   ← Обертка state machine
├── docs/
│   ├── eval_logging_ru.md   ← Краткая инструкция (RU)
│   ├── eval_logging.md      ← Полная документация (EN)
│   └── env_setup_ru.md      ← Настройка .env
└── EVAL_LOGGING_READY.md    ← Полная сводка
```

## 🚀 Примеры использования

### Тестовый запуск (2 кейса)
```bash
python test_eval_logging.py
```

### Полный eval с логированием
```bash
python -m cmm.eval \
  --dataset eval_intake_fix_final/dataset.csv \
  --mode real \
  --judge-mode llm \
  --limit 5
```

### Запуск существующих тестов
```bash
# Логирование включится автоматически при mode=real
python -m cmm.eval --dataset path/to/dataset.csv --mode real --judge-mode llm
```

## 📊 Что вы увидите

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
Estimated cost: $0.0006
================================================================================
```

## ❓ Где взять API ключ

### DeepSeek (рекомендуется)
1. https://platform.deepseek.com/
2. Зарегистрируйтесь
3. API Keys → Create new key
4. Скопируйте в .env

### OpenAI
1. https://platform.openai.com/
2. API Keys → Create new key
3. Скопируйте в .env как `OPENAI_API_KEY`

## 🔧 Проверка настройки

```bash
python -c "from Lib.AI_request import _get_api_key; print('✓ API key OK')"
```

Если видите `✓ API key OK` - всё готово!

## 📚 Документация

- **Быстрый старт**: `docs/eval_logging_ru.md`
- **Настройка .env**: `docs/env_setup_ru.md`
- **Полная документация**: `docs/eval_logging.md`
- **Список изменений**: `EVAL_LOGGING_CHANGELOG.md`

## 💡 Важно

- ✅ Файл `.env` уже в `.gitignore` - не попадет в git
- ✅ Логирование не влияет на результаты тестов
- ✅ Оценка токенов приблизительная (~0.75 на слово)
- ✅ Можно отключить: `set_logger_enabled(False)`

## 🎉 Готово к использованию!

1. Создайте `.env` из шаблона
2. Вставьте API ключ
3. Запустите `python test_eval_logging.py`
4. Наслаждайтесь подробным логированием!
