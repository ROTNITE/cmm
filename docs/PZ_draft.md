# Пояснительная записка: Collective Meta-Moderation MVP

## Назначение и область применения

Collective Meta-Moderation — экспериментальный программный MVP для подготовки ответа на пользовательский запрос через последовательный процесс коллективной метамодерации.

Система предназначена для локальных экспериментов с многоэтапным reasoning-пайплайном: безопасный query intake, экспертные перспективы, анализ баланса, смысловой анализ конфликтов/консенсуса, структурированный deliberation round, планирование, критика, генерация ответа, модерация и трассировка результата.

Важно: наличие нескольких агентов само по себе не гарантирует более высокое качество. Реализация делает экспертный вклад явным и передает его в downstream-этапы, а качество предлагается проверять через evaluation harness.

## Технические характеристики

- Язык: Python.
- Основной API: `Lib.orchestrator.run_cmm(query, max_iters=2, model="deepseek-chat")`.
- CLI запуска CMM: `python main.py`.
- CLI оценки: `python -m cmm.eval --dataset cmm_dataset_v1.csv --mode mock`.
- CLI real-evaluation: `python -m cmm.eval --dataset cmm_dataset_v1.csv --mode real --judge-mode none|llm`.
- Зависимости: `openai`, `python-dotenv`.
- Тесты: стандартный `unittest`.
- Секреты: API-ключи должны храниться локально в `.env`; реальные ключи не должны попадать в репозиторий.

## Описание алгоритма

Фактический MVP-пайплайн:

1. Сохранить `original_query`.
2. Выполнить `query_intake`: сохранить исходный запрос как authoritative source, построить `cleaned_query` как helper text и извлечь контекст, ограничения, критерии успеха, неизвестные и пользовательские предпочтения.
3. Выбрать и запустить экспертную панель.
4. Собрать `expert_bundle`.
5. Выполнить анализ баланса перспектив.
6. Построить `deliberation_brief`.
7. Выполнить semantic conflict / consensus analysis: выявить согласия, разногласия, trade-offs, blind spots и риски преждевременного консенсуса.
8. Выполнить `meta_moderator` для оценки качества процесса.
9. Если conflict/meta-состояние требует обсуждения, запустить один structured deliberation round: выбранные эксперты видят позиции других ролей, фиксируют согласия/возражения, упущения, revised recommendations, новые риски и вопросы группы.
10. Объединить deliberation-derived contributions с исходным `expert_bundle`.
11. Повторно выполнить анализ баланса, перестроить `deliberation_brief` и повторно выполнить semantic conflict / consensus analysis.
12. Если `meta_moderator` возвращает `DEEPEN` или `ADD_EXPERT` и targeted follow-up всё ещё полезен, выбрать целевые базовые роли для второго экспертного раунда.
13. Запустить последовательный targeted second expert round.
14. Объединить вклады экспертных раундов.
15. Повторно выполнить анализ баланса перспектив.
16. Перестроить итоговый `deliberation_brief`.
17. Повторно выполнить semantic conflict / consensus analysis по объединённому expert bundle.
18. Сгенерировать план на основе формализованного запроса и итогового экспертного brief.
19. Проверить план критиком.
20. Сгенерировать ответ и выполнить moderation/revision loop.
21. Вернуть `final_answer`, `trace_report` и raw-данные.

## Входные и выходные данные

Вход:

- пользовательский запрос `query`;
- опционально локальная среда с API-ключом для real model calls;
- для evaluation: CSV-датасет `cmm_dataset_v1.csv`.

Выход `run_cmm`:

```python
{
    "final_answer": str,
    "trace_report": dict,
    "raw": {
        "expert_bundle": dict,
        "moderated_result": dict,
    },
}
```

`trace_report` содержит исходный и формализованный запрос, роли экспертов, экспертные раунды, deliberation rounds/revisions, balance reports, conflict reports, meta moderation decisions, plan, critique, moderation reports, revision count, confidence и warnings.

`original_query` является источником истины. `formalized_query` заполняется из `cleaned_query` и используется только как вспомогательный текст; downstream-агенты также получают структурированный `query_intake`.

## Состав программных средств

- `main.py`: CLI-обертка.
- `Lib/orchestrator.py`: центральный пайплайн.
- `Lib/query_intake.py`: безопасный входной слой, который сохраняет `original_query` и извлекает `cleaned_query`, контекст, ограничения, критерии успеха, неизвестные и предпочтения.
- `Lib/expert_*`: роли, выбор ролей, экспертные вклады и панель.
- `Lib/expert_rounds.py`: выбор целевых ролей для второго экспертного раунда, запуск follow-up экспертов и объединение expert bundles.
- `Lib/balance_analyzer.py`: анализ баланса.
- `Lib/conflict_analyzer.py`: смысловой анализ согласий, разногласий, trade-offs, blind spots и рисков преждевременного консенсуса.
- `Lib/deliberation.py`: синтез экспертного brief.
- `Lib/deliberation_round.py`: структурированный раунд, где выбранные эксперты отвечают на позиции других ролей и пересматривают рекомендации.
- `Lib/meta_moderator.py`: управление процессом.
- `Lib/plan_development.py`: JSON-first планировщик.
- `Lib/agent_moderator.py`: модерация ответа и revision loop.
- `Lib/json_utils.py`: безопасный разбор JSON-like output.
- `cmm/eval.py`: evaluation harness.
- `tests/`: offline unit tests.

## Ожидаемые показатели

На текущем этапе не заявляется, что CMM стабильно лучше baseline. Ожидаемый показатель для MVP — воспроизводимая трассировка, безопасные fallback-и, прохождение offline-тестов и возможность сравнить baseline vs CMM на `cmm_dataset_v1.csv`.

Evaluation harness считает эвристические метрики покрытия:

- покрытие обязательных пунктов рубрики;
- покрытие ожидаемых перспектив;
- покрытие ожидаемых failure modes/рисков.

Эти метрики не являются научным доказательством качества и должны использоваться как regression/evaluation aid.

Real judged evaluation является отдельным opt-in режимом. Он формирует baseline-ответ и CMM-ответ, сохраняет trace CMM, строит blind Answer A/B пакет и либо экспортирует файл для человеческой оценки (`judge-mode none`), либо вызывает LLM judge (`judge-mode llm`). Рубрики и ожидаемые перспективы используются как критерии оценки судьи, а не как скрытое содержимое для генерации ответов.

## Источники

- Локальный датасет: `cmm_dataset_v1.csv`.
- Исходный код проекта: модули `Lib/` и `cmm/`.
- Локальные тесты: `tests/`.

## Ограничения

- Второй экспертный раунд есть, но он ограничен: он последовательный, использует существующие базовые роли и является targeted follow-up, а не свободной дискуссией.
- Structured deliberation round есть, но он ограничен одной schema-driven итерацией и не является полноценной свободной debate/state-machine системой.
- Query intake защищает исходный запрос от перезаписи, но сам по себе не доказывает повышение качества downstream-ответов.
- Нет fully free-form прямой дискуссии экспертов друг с другом.
- Нет параллельного запуска агентов.
- Нет произвольной генерации новых ролей.
- Анализ баланса пока основан преимущественно на тегах перспектив.
- Semantic conflict analysis помогает выявлять trade-offs и риски преждевременного консенсуса, а structured deliberation round помогает экспертам ответить на позиции друг друга, но это всё ещё ограниченный MVP-механизм.
- Нет UI.
- Реальные LLM-вызовы зависят от API-ключа и внешней доступности модели.
- Mock evaluation не является доказательством качества или реальным сравнением моделей.
- Real judged evaluation даёт только первые ограниченные evidence по выборке и не является доказательством универсального превосходства CMM.
