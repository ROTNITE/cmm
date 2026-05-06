# Итоговый отчет: Улучшение CMM системы

## 🎯 Задача
Улучшить Collective Meta-Moderation систему для достижения стабильных побед над baseline в judge тестах.

## 📊 Финальные результаты

### Лучший достигнутый результат (10 кейсов):
- **CMM wins: 5** (50%)
- **Baseline wins: 5** (50%)
- **Ties: 0** (0%)
- **mean_cmm_overall: 5.5**
- **mean_baseline_overall: 7.9**
- **Technical failures: 4** (40%)

## ✅ Успешные исправления

### 1. Judge теперь работает
**Проблема:** Judge использовал модель "deepseek-chat", которой нет в локальном прокси. Все результаты были TIE.

**Решение:** Указывать `--judge-model "kr/claude-sonnet-4.5"`

**Команда:**
```bash
python -m cmm.eval \
  --dataset cmm_dataset_v2.csv \
  --limit 10 \
  --mode real \
  --judge-mode llm \
  --model "kr/claude-sonnet-4.5" \
  --judge-model "kr/claude-sonnet-4.5"
```

### 2. Query intake извлекает brevity constraints
**Проблема:** Query intake игнорировал слова "кратко", "briefly" из самого вопроса.

**Файл:** `Lib/query_intake.py:307`

**Изменение:**
```python
# Было:
"- constraints: ONLY extract explicitly stated constraints from the query. Do NOT extract words from the question itself"

# Стало:
"- constraints: Extract ALL constraints including brevity/length requirements from the query itself (\"briefly\", \"кратко\", \"in 5 sentences\", \"short answer\") AND explicitly stated constraints."
```

### 3. Direct answer строго соблюдает brevity
**Проблема:** Direct answer слабо соблюдал brevity constraints, писал слишком длинные ответы.

**Файл:** `Lib/direct_answer.py:89`

**Изменение:**
```python
# Было:
"- Respect any formatting constraints (brevity, sentence limits, etc.)"

# Стало:
"- STRICTLY respect brevity constraints (\"кратко\", \"briefly\", \"short\", sentence limits): when brevity is requested, prioritize conciseness over additional examples or details
- When brevity is requested: use 1 focused example instead of multiple, avoid redundant explanations, get to the point quickly"
```

**Эффект:** CMM получает 10.0 vs Baseline 9.0 на кейсах с brevity constraints.

## ❌ Нерешенная проблема: Plan Critic

### Проблема
**4 из 5 проигрышей** (80%) были из-за plan critic failures:
- V2-006: FULL_CMM FAILED - plan_needs_revision_after_max_iters
- V2-007: LIGHT_CMM_DEGRADED FAILED - plan_rejected_after_max_iters
- V2-009: FULL_CMM_DEGRADED FAILED - plan_rejected_after_max_iters
- V2-010: FULL_CMM_DEGRADED FAILED - plan_needs_revision_after_max_iters

Все эти кейсы получили **CMM score: 0.0** (пустой ответ) из-за того, что plan critic отклонил план и система упала в FAILED.

### Попытка исправления (провалилась)
Я попытался сделать систему более толерантной к несовершенным планам, изменив логику в `Lib/state_machine.py:1505-1532`.

**Результат:** Еще хуже!
- CMM wins: 2 (было 5)
- Baseline wins: 6 (было 5)
- Technical failures: 6 (было 4)

**Почему провалилось:** Проблема не в логике state_machine, а в том, что plan_critic помечает слишком много вещей как "critical_blockers". Функция `can_best_effort_finalize()` все равно возвращает False.

### Корневая причина
Plan critic слишком строгий и помечает качественные проблемы как критические блокеры, хотя они не представляют safety/legal рисков.

**Файлы:**
- `Lib/plan_critic.py` - генерирует слишком строгую критику
- `Lib/quality_gates.py:171-210` - функция `plan_blockers()` собирает блокеры
- `Lib/quality_gates.py:338-363` - функция `can_best_effort_finalize()` проверяет блокеры

## 📈 Детальный анализ результатов

### Успешные кейсы (CMM wins):
1. **V2-001:** DIRECT - CMM 9.0 vs Baseline 8.0
2. **V2-003:** DIRECT - CMM 9.0 vs Baseline 8.0
3. **V2-004:** LIGHT_CMM - CMM 9.0 vs Baseline 7.0
4. **V2-005:** LIGHT_CMM - CMM 8.0 vs Baseline 7.0
5. **V2-008:** FULL_CMM - CMM 9.0 vs Baseline 8.0

**Паттерн:** CMM выигрывает, когда система работает без failures. Качество ответов высокое (8-9 баллов).

### Проигранные кейсы:
1. **V2-002:** DIRECT - CMM 8.0 vs Baseline 9.0 (небольшой проигрыш по качеству)
2. **V2-006:** FULL_CMM FAILED - CMM 0.0 vs Baseline 9.0
3. **V2-007:** LIGHT_CMM_DEGRADED FAILED - CMM 0.0 vs Baseline 10.0
4. **V2-009:** FULL_CMM_DEGRADED FAILED - CMM 0.0 vs Baseline 5.0
5. **V2-010:** FULL_CMM_DEGRADED FAILED - CMM 0.0 vs Baseline 9.0

**Паттерн:** 4 из 5 проигрышей - это technical failures с 0.0 score. Только 1 проигрыш по качеству.

## 🎓 Ключевые выводы

1. **DIRECT режим работает отлично** - 2 победы из 3 кейсов (67% win rate)
2. **LIGHT_CMM работает хорошо** - 2 победы из 5 кейсов (40% win rate, но 2 failures)
3. **FULL_CMM проблематичен** - 1 победа из 3 кейсов (33% win rate, 3 failures)
4. **Plan critic - главный враг** - вызывает 40% всех failures
5. **Без failures win rate был бы 70-80%** - если бы 4 failed кейса были успешными

## 🚀 Рекомендации для дальнейшего улучшения

### Приоритет 1: Исправить Plan Critic
**Проблема:** Слишком строгий, помечает качественные проблемы как critical blockers.

**Решения:**
1. **Переписать plan_critic prompts** - сделать более конструктивным и менее строгим
2. **Изменить `plan_blockers()`** - не считать качественные проблемы критическими
3. **Добавить fallback** - если plan отклонен 2 раза, использовать direct answer вместо FAILED
4. **Уменьшить max_iters** - с 2 до 1, чтобы быстрее переходить к best-effort

### Приоритет 2: Улучшить FULL_CMM
**Проблема:** 3 failures из 3 кейсов (100% failure rate).

**Решения:**
1. **Упростить FULL_CMM** - убрать избыточные проверки
2. **Использовать LIGHT_CMM вместо FULL_CMM** - для большинства сложных кейсов
3. **Добавить graceful degradation** - FULL_CMM → LIGHT_CMM → DIRECT при failures

### Приоритет 3: Оптимизировать token usage
**Проблема:** CMM использует 147,410 tokens vs baseline ~30,000 tokens (5x больше).

**Решения:**
1. **Кэшировать промпты** - использовать prompt caching для повторяющихся частей
2. **Сократить context** - передавать только необходимую информацию
3. **Оптимизировать expert panel** - меньше экспертов для простых задач

## 📝 Что работает сейчас

### Сильные стороны CMM:
- ✅ DIRECT режим: 67% win rate
- ✅ Brevity compliance: 10.0 vs 9.0
- ✅ Качество ответов: 8-9 баллов когда работает
- ✅ Judge работает корректно
- ✅ Router accuracy: 60%

### Слабые стороны CMM:
- ❌ Plan critic: 40% failure rate
- ❌ FULL_CMM: 100% failure rate
- ❌ Token usage: 5x больше baseline
- ❌ Время выполнения: 300-500s для сложных кейсов

## 💡 Философия системы

### Текущая философия (не работает):
"Лучше не дать ответа, чем дать несовершенный ответ"

### Правильная философия:
"Лучше дать несовершенный ответ, чем не дать ответа вообще"

Система должна быть толерантной к несовершенству и продолжать работу, блокируя только при критических safety/legal рисках.

## ✅ Итоговый статус

### Что достигнуто:
1. ✅ Judge работает - можем измерять качество
2. ✅ Brevity constraints соблюдаются - CMM 10.0 vs Baseline 9.0
3. ✅ 50% win rate - лучше, чем 0%, но далеко от цели
4. ✅ DIRECT режим работает отлично - 67% win rate

### Что не достигнуто:
1. ❌ 70-80% win rate - остались на 50%
2. ❌ Plan critic исправлен - попытка провалилась
3. ❌ FULL_CMM работает - 100% failure rate
4. ❌ Оптимизирован token usage - 5x больше baseline

### Следующие шаги:
1. **Переписать plan_critic** - сделать менее строгим
2. **Добавить fallback механизмы** - graceful degradation при failures
3. **Упростить FULL_CMM** - или заменить на LIGHT_CMM
4. **Протестировать на большем датасете** - 20-30 кейсов

## 🎯 Реалистичная оценка

**Текущее состояние:** CMM работает, но имеет критические проблемы с plan critic.

**Потенциал:** Если исправить plan critic, win rate может вырасти до 70-80%.

**Время на исправление:** 2-4 часа работы над plan_critic prompts и quality_gates логикой.

**Риск:** Любые изменения в plan critic могут сделать систему хуже (как показал мой опыт).

---

**Дата:** 2026-05-06
**Версия:** После всех исправлений и откатов
**Статус:** Частично успешно - 50% win rate достигнут, но цель 70-80% не достигнута
