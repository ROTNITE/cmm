# Настройка OmniRoute для использования Claude API

## Зачем это нужно?

Вместо DeepSeek мы будем использовать Claude Sonnet 4.5 через OmniRoute:
- **Лучшее качество** - Claude сильнее DeepSeek
- **Лучший JSON parsing** - меньше fallback'ов
- **Более надёжная генерация**

## Шаг 1: Получить API ключ из OmniRoute

1. Запусти OmniRoute
2. Открой в браузере: http://localhost:20128/dashboard
3. Зайди в Dashboard → API Manager
4. Нажми Create API Key / Add API Key / New Key
5. Скопируй ключ вида: `sk-...`

## Шаг 2: Проверить ключ

```bash
curl http://localhost:20128/v1/models \
  -H "Authorization: Bearer ТВОЙ_OMNIROUTE_KEY"
```

Должен вернуть список доступных моделей, включая `kr/claude-sonnet-4.5`.

## Шаг 3: Настроить .env

Отредактируй файл `.env` в корне проекта:

```bash
# OmniRoute API ключ
OMNIROUTE_API_KEY=sk-твой-ключ-omniroute

# OmniRoute base URL (локальный)
OMNIROUTE_BASE_URL=http://localhost:20128/v1

# Модель по умолчанию
# Для быстрых тестов: kr/claude-sonnet-4.5
# Для максимального качества: kr/claude-opus-4.7 (если доступен)
DEFAULT_MODEL=kr/claude-sonnet-4.5
```

## Шаг 4: Запустить eval

```bash
# С явным указанием модели
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 5 --mode real --judge-mode llm --model kr/claude-sonnet-4.5 --output-dir eval_claude

# Или использовать модель по умолчанию из .env
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 5 --mode real --judge-mode llm --output-dir eval_claude
```

## Как это работает?

Код в `Lib/AI_request.py` уже поддерживает OmniRoute:

1. `_get_api_key()` ищет ключи в порядке:
   - OMNIROUTE_API_KEY
   - CLAUDE_API_KEY
   - DEEPSEEK_API_KEY
   - OPENAI_API_KEY

2. `_get_base_url()` ищет base URL в порядке:
   - OMNIROUTE_BASE_URL
   - CLAUDE_BASE_URL
   - OPENAI_BASE_URL
   - DEFAULT_BASE_URL (DeepSeek)

3. `send_to_AI()` использует OpenAI-compatible API, который работает с OmniRoute

## Рекомендуемые модели

Для разных задач:

- **kr/claude-sonnet-4.5** - баланс скорости и качества (рекомендуется для начала)
- **kr/claude-opus-4.7** - максимальное качество (если доступен в OmniRoute)
- **kr/claude-haiku-4.5** - максимальная скорость для простых задач

## Troubleshooting

### Ошибка: "API key is not configured"
- Проверь, что OMNIROUTE_API_KEY прописан в .env
- Проверь, что .env находится в корне проекта
- Попробуй перезапустить Python процесс

### Ошибка: "Connection refused"
- Проверь, что OmniRoute запущен
- Проверь, что OMNIROUTE_BASE_URL = http://localhost:20128/v1
- Попробуй открыть http://localhost:20128/dashboard в браузере

### Ошибка: "Model not found"
- Проверь список доступных моделей через curl
- Убедись, что модель kr/claude-sonnet-4.5 доступна в твоём OmniRoute
