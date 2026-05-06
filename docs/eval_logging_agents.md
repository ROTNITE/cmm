# Обновление: Автоматическое логирование всех агентов

## Что изменилось

Теперь система **автоматически определяет и логирует все внутренние агенты CMM** без необходимости создавать обертки для каждого агента.

## Как это работает

### Автоматическое определение агентов

Система анализирует промпты к AI и автоматически определяет, какой агент делает вызов:

- 🔀 **Router** - определение режима работы (DIRECT/LIGHT_CMM/FULL_CMM)
- 🧠 **Query Intake** - анализ и очистка запроса
- 👤 **Expert Agent** - вклад эксперта (strategy, user, risk и т.д.)
- 📋 **Planner** - разработка плана действий
- 🔍 **Plan Critic** - критика и оценка плана
- 🤝 **Meta Moderator** - синтез мнений экспертов
- 🛡️ **Answer Moderator** - проверка качества ответа
- ⚖️ **Balance Analyzer** - анализ баланса перспектив
- 🔄 **Conflict Analyzer** - анализ конфликтов
- 💬 **Deliberation** - раунды обсуждения
- ⚡ **Direct Answer** - прямой ответ без CMM
- ⚖️ **Judge** - оценка ответов в eval тестах
- 📊 **Baseline** - базовый ответ для сравнения

## Что вы увидите в логах

### Пример полного лога с агентами:

```
================================================================================
🔍 CASE: CASE-1
Query: How to improve student engagement in hybrid university?
================================================================================

▶ Stage: BASELINE
  💬 AI Call #1 [baseline]
    Model: deepseek-chat
    Tokens: 45 prompt + 320 completion = 365 total
    Running total: 365 tokens
  ✓ BASELINE complete

▶ Stage: CMM
  Starting CMM state machine (route_mode=AUTO)
  
  💬 AI Call #2 [query_intake]
    Model: deepseek-chat
    Tokens: 80 prompt + 120 completion = 200 total
    Running total: 565 tokens
  
  💬 AI Call #3 [router]
    Model: deepseek-chat
    Tokens: 150 prompt + 80 completion = 230 total
    Running total: 795 tokens
  🔀 Router: LIGHT_CMM (complexity: medium)
    Reasoning: Query requires multiple perspectives...
  
  💬 AI Call #4 [expert_agent]
    Model: deepseek-chat
    Tokens: 250 prompt + 400 completion = 650 total
    Running total: 1445 tokens
  👤 Expert: strategy_expert (strategy) - valid
  
  💬 AI Call #5 [expert_agent]
    Model: deepseek-chat
    Tokens: 250 prompt + 380 completion = 630 total
    Running total: 2075 tokens
  👤 Expert: user_experience (user) - valid
  
  💬 AI Call #6 [expert_agent]
    Model: deepseek-chat
    Tokens: 250 prompt + 390 completion = 640 total
    Running total: 2715 tokens
  👤 Expert: risk_analyst (risk) - valid
  
  💬 AI Call #7 [balance_analyzer]
    Model: deepseek-chat
    Tokens: 180 prompt + 150 completion = 330 total
    Running total: 3045 tokens
  
  💬 AI Call #8 [conflict_analyzer]
    Model: deepseek-chat
    Tokens: 200 prompt + 180 completion = 380 total
    Running total: 3425 tokens
  
  💬 AI Call #9 [meta_moderator]
    Model: deepseek-chat
    Tokens: 300 prompt + 250 completion = 550 total
    Running total: 3975 tokens
  🤝 Meta moderator: sufficient consensus
  
  💬 AI Call #10 [planner]
    Model: deepseek-chat
    Tokens: 400 prompt + 500 completion = 900 total
    Running total: 4875 tokens
  
  💬 AI Call #11 [plan_critic]
    Model: deepseek-chat
    Tokens: 350 prompt + 200 completion = 550 total
    Running total: 5425 tokens
  📋 Plan critique: APPROVED
  
  💬 AI Call #12 [answer_moderator]
    Model: deepseek-chat
    Tokens: 450 prompt + 180 completion = 630 total
    Running total: 6055 tokens
  🛡️ Moderation: APPROVED
  
  CMM completed with state: FINALIZE
  ✓ CMM complete

▶ Stage: JUDGE
  💬 AI Call #13 [judge]
    Model: deepseek-chat
    Tokens: 890 prompt + 150 completion = 1040 total
    Running total: 7095 tokens
  ✓ JUDGE complete

🏆 Winner: CMM
Time: 15.8s
================================================================================

📊 EVALUATION SUMMARY
Total AI calls: 13
Total tokens used: 7,095
Estimated cost: $0.0015
================================================================================
```

## Технические детали

### Обновленные файлы:

1. **Lib/AI_request_instrumented.py**
   - Добавлена функция `_infer_purpose_from_prompt()` 
   - Автоматически определяет тип агента по содержимому промпта
   - Логирует каждый вызов с правильным назначением

2. **Lib/json_retry.py**
   - Использует инструментированную версию при `CMM_EVAL_LOGGING=1`
   - Все JSON-агенты автоматически логируются

3. **Lib/direct_answer.py**
   - Использует инструментированную версию при `CMM_EVAL_LOGGING=1`
   - Direct answer режим логируется

## Преимущества

✅ **Автоматическое определение** - не нужно вручную указывать тип агента  
✅ **Полное покрытие** - логируются ВСЕ агенты CMM  
✅ **Нулевое влияние** - работает только при `CMM_EVAL_LOGGING=1`  
✅ **Подробная статистика** - видно каждый шаг и расход токенов  
✅ **Легко отключить** - просто не используйте `mode=real` в eval  

## Использование

Ничего не изменилось! Просто запускайте eval как обычно:

```bash
python test_eval_logging.py
```

или

```bash
python -m cmm.eval --dataset data.csv --mode real --judge-mode llm
```

Теперь вы увидите **все внутренние агенты** с их вызовами и токенами!
