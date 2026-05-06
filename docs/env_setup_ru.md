# Настройка .env файла

## Быстрая настройка

1. **Скопируйте шаблон:**
   ```bash
   cp .env.template .env
   ```

2. **Откройте .env в текстовом редакторе:**
   ```bash
   notepad .env
   # или
   code .env
   ```

3. **Вставьте ваш API ключ:**
   ```env
   OMNIROUTE_API_KEY=sk-ваш-ключ-здесь
   ```

4. **Сохраните файл**

## Пример готового .env

```env
# Основной API ключ
OMNIROUTE_API_KEY=sk-1234567890abcdef1234567890abcdef

# Опционально: включить подробное логирование
CMM_EVAL_LOGGING=1
```

## Где взять API ключ

### DeepSeek (рекомендуется)
1. Зайдите на https://platform.deepseek.com/
2. Зарегистрируйтесь или войдите
3. Перейдите в раздел API Keys
4. Создайте новый ключ
5. Скопируйте ключ в .env как `OMNIROUTE_API_KEY` или `DEEPSEEK_API_KEY`

### OpenAI
1. Зайдите на https://platform.openai.com/
2. Перейдите в API Keys
3. Создайте новый ключ
4. Скопируйте ключ в .env как `OPENAI_API_KEY`

## Проверка настройки

Запустите тест:
```bash
python -c "from Lib.AI_request import _get_api_key; print('✓ API key configured')"
```

Если видите `✓ API key configured` - всё настроено правильно!

## Безопасность

- ✅ Файл `.env` уже добавлен в `.gitignore`
- ✅ Никогда не коммитьте `.env` в git
- ✅ Не делитесь API ключами
- ✅ Используйте `.env.template` для примеров

## Приоритет ключей

Если указано несколько ключей, используется первый найденный:
1. `OMNIROUTE_API_KEY`
2. `CLAUDE_API_KEY`
3. `DEEPSEEK_API_KEY`
4. `OPENAI_API_KEY`

## Альтернативные базовые URL

Если используете прокси или другой endpoint:

```env
OMNIROUTE_API_KEY=your_key
OMNIROUTE_BASE_URL=https://your-proxy.com/v1
```

## Troubleshooting

### Ошибка: "API key is not configured"
- Проверьте, что файл `.env` существует в корне проекта
- Проверьте, что ключ указан без пробелов и кавычек
- Проверьте имя переменной (должно быть одно из: OMNIROUTE_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY)

### Ошибка: "Error: openai package is not available"
```bash
pip install openai
```

### Ошибка при чтении .env
- Убедитесь, что файл в кодировке UTF-8
- Проверьте, что нет лишних символов
- Используйте формат: `KEY=value` (без пробелов вокруг =)
