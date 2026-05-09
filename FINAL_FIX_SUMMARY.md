# Финальное исправление: Судья не работал из-за неправильной модели

**Дата:** 2026-05-08  
**Статус:** ✅ ИСПРАВЛЕНО

---

## 🔴 Критическая проблема

После всех предыдущих исправлений (порог TIE, логика планировщика, логирование) тесты всё равно показывали 100% TIE с нулевыми оценками.

### Симптомы
```
Winner: TIE
Baseline overall: 0.0/10
CMM overall: 0.0/10
Reason: Judge output could not be parsed; marked as tie for review.
```

---

## 🔍 Диагностика

### Шаг 1: Проверка raw_judge_output
```bash
python -c "
import json
with open(r'C:\cmm-main\eval_results\cases_incremental.jsonl', 'r', encoding='utf-8') as f:
    case = json.loads(f.readline())
    print(case.get('raw_judge_output', ''))
"
```

**Результат:**
```
Error: Error code: 400 - {'error': {'message': 'No credentials for provider: aimlapi', 'type': 'invalid_request_error', 'code': 'bad_request'}}
```

### Шаг 2: Анализ причины
Судья использовал модель `deepseek-chat` по умолчанию, которая требует провайдера `aimlapi`. У пользователя нет credentials для этого провайдера, поэтому все вызовы судьи падали с ошибкой 400.

---

## ✅ Решение

Изменена дефолтная модель судьи с `deepseek-chat` на `kr/claude-sonnet-4.5` (та же модель, что используется для CMM и baseline).

### Изменения в `cmm/eval.py`

**1. Функция `judge_case_with_llm` (строка 691):**
```python
# Было:
def judge_case_with_llm(case: dict, baseline: dict, cmm: dict, model: str = "deepseek-chat") -> dict:

# Стало:
def judge_case_with_llm(case: dict, baseline: dict, cmm: dict, model: str = "kr/claude-sonnet-4.5") -> dict:
```

**2. Функция `score_case_judged` (строка 778):**
```python
# Было:
def score_case_judged(
    case: dict,
    baseline: dict,
    cmm: dict,
    *,
    judge_mode: str = "none",
    judge_model: str = "deepseek-chat",
) -> dict:

# Стало:
def score_case_judged(
    case: dict,
    baseline: dict,
    cmm: dict,
    *,
    judge_mode: str = "none",
    judge_model: str = "kr/claude-sonnet-4.5",
) -> dict:
```

**3. Аргумент командной строки (строка 1325):**
```python
# Было:
parser.add_argument("--judge-model", default="deepseek-chat", help="Model for --judge-mode llm")

# Стало:
parser.add_argument("--judge-model", default="kr/claude-sonnet-4.5", help="Model for --judge-mode llm")
```

### Дополнительное исправление: кодировка в логгере

**Файл:** `Lib/eval_logger_enhanced.py` (строка 163)

Добавлена безопасная обработка non-ASCII символов в reason:
```python
if reason:
    # Encode safely for Windows console
    try:
        reason_safe = reason[:200].encode('ascii', 'replace').decode('ascii')
    except:
        reason_safe = "[reason contains non-ASCII characters]"
    self._print(f"    Reason: {reason_safe}", level=1)
```

---

## 🧪 Проверка исправления

### Тест на 2 кейсах
```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 2 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"
```

**Результаты:**
```
Case V2-001:
  Baseline overall: 8.00/10
  CMM overall: 9.00/10
  Delta: +1.00
  Winner: CMM ✅

Case V2-002:
  Baseline overall: 9.00/10
  CMM overall: 9.00/10
  Delta: +0.00
  Winner: TIE ✅
```

**Статистика:**
- CMM wins: 1 (50%)
- Baseline wins: 0 (0%)
- Ties: 1 (50%)
- Время на кейс: ~25 секунд

---

## 📊 Ожидаемые результаты полного теста

### До исправления
- CMM wins: 0%
- Baseline wins: 0%
- Ties: 100% (все с нулевыми оценками)
- Причина: "Judge output could not be parsed"

### После исправления
- CMM wins: 30-50%
- Baseline wins: 20-30%
- Ties: 20-40%
- Все оценки корректные (не нулевые)
- Судья возвращает валидный JSON с детальными оценками

---

## 🎯 Итоговый список всех исправлений

1. ✅ **Порог TIE:** увеличен с 0.5 до 1.0
2. ✅ **Промпт судьи:** добавлены инструкции о решительности
3. ✅ **Логика планировщика:** смягчена (допускается до 3 minor blockers)
4. ✅ **Детальное логирование:** добавлен `eval_logger_enhanced.py`
5. ✅ **Инкрементальная запись:** результаты сохраняются после каждого кейса
6. ✅ **Модель судьи:** изменена с deepseek-chat на kr/claude-sonnet-4.5
7. ✅ **Кодировка логов:** безопасная обработка non-ASCII символов

---

## 📝 Команды для запуска

### Короткий тест (2 кейса)
```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 2 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"
```

### Полный тест (20 кейсов)
```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode llm --model "kr/claude-sonnet-4.5"
```

### Мониторинг прогресса
```bash
# Windows PowerShell
while ($true) { cls; cat eval_results/progress.json; sleep 5 }
```

---

## ✅ Проверочный чеклист

- [x] Судья использует правильную модель (kr/claude-sonnet-4.5)
- [x] Судья возвращает валидный JSON
- [x] Оценки не нулевые
- [x] Winner не всегда TIE
- [x] Reason содержит осмысленное объяснение
- [x] Логи выводятся без ошибок кодировки
- [x] Инкрементальные файлы обновляются
- [ ] Полный тест (20 кейсов) завершен
- [ ] Финальные метрики соответствуют ожиданиям

---

## 🔍 Как это обнаружили

1. Заметили что все результаты - TIE с нулевыми оценками
2. Проверили `results_incremental.csv` - все reason = "Judge output could not be parsed"
3. Проверили `cases_incremental.jsonl` - поле `raw_judge_output` содержало ошибку API
4. Увидели ошибку: "No credentials for provider: aimlapi"
5. Нашли что судья использует `deepseek-chat` вместо доступной модели
6. Изменили дефолтную модель на `kr/claude-sonnet-4.5`
7. Проверили - судья заработал!

---

**Конец документа**
