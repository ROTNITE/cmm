# Пояснительная записка: Collective Meta-Moderation MVP

## Назначение и область применения

Collective Meta-Moderation — экспериментальный программный MVP для подготовки ответа на пользовательский запрос через последовательный процесс коллективной метамодерации.

Система предназначена для локальных экспериментов с многоэтапным reasoning-пайплайном: безопасный query intake, экспертные перспективы, анализ баланса, смысловой анализ конфликтов/консенсуса, структурированный deliberation round, планирование, критика, генерация ответа, модерация и трассировка результата.

Важно: наличие нескольких агентов само по себе не гарантирует более высокое качество. Реализация делает экспертный вклад явным и передает его в downstream-этапы, а качество предлагается проверять через evaluation harness.

## Технические характеристики

- Язык: Python.
- Основной API: `Lib.orchestrator.run_cmm(query, max_iters=2, model="deepseek-chat", route_mode="AUTO", parallel_mode="SEQUENTIAL", max_workers=None, max_deliberation_rounds=1)`; старые вызовы без новых optional параметров сохраняются, внутри выполнение делегируется bounded CMM state machine. `max_deliberation_rounds` ограничен диапазоном `1..2`.
- CLI запуска CMM: `python main.py`; компактный trace demo: `python main.py --trace-summary "query"`.
- CLI оценки: `python -m cmm.eval --dataset cmm_dataset_v1.csv --mode mock` или `python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode mock`.
- CLI real-evaluation: `python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode none|llm`.
- Зависимости: `openai`, `python-dotenv`.
- Тесты: стандартный `unittest`.
- Секреты: API-ключи должны храниться локально в `.env`; реальные ключи не должны попадать в репозиторий.

## Описание алгоритма

Фактический MVP-пайплайн теперь управляется явной state machine:

1. `INTAKE`: сохранить `original_query` и выполнить `query_intake`.
2. `ROUTE`: deterministic router выбирает `DIRECT`, `LIGHT_CMM` или `FULL_CMM`.
3. `DIRECT_ANSWER`: для простых low-risk задач вернуть прямой ответ без expert/balance/conflict/meta/planning stages.
4. `PANEL_ROUND_1`: для `LIGHT_CMM` и `FULL_CMM` выбрать и запустить экспертную панель. По умолчанию экспертные вызовы последовательные; opt-in `parallel_mode="THREADS"` может выполнять только независимые экспертные вызовы через bounded thread pool.
5. `BALANCE`: выполнить анализ баланса и построить `deliberation_brief`.
6. `PLAN`: для `LIGHT_CMM` перейти к планированию без conflict/meta/deliberation/second-round stages.
7. `CONFLICT_ANALYSIS`: для `FULL_CMM` выявить согласия, разногласия, trade-offs, blind spots и риски преждевременного консенсуса.
8. `META_DECISION`: принять process-level решение.
9. `DELIBERATION_ROUND`: при необходимости запустить structured deliberation round.
10. `CONSENSUS_CHECK`: после deliberation обновить balance/brief/conflict; при `max_deliberation_rounds=2` запустить второй deliberation round только для unresolved high-severity conflicts с явно определёнными ролями.
11. `META_RECHECK`: после изменений deliberation/extra round проверить, можно ли перейти к планированию или нужен targeted follow-up.
12. `PANEL_ROUND_EXTRA`: при необходимости запустить один targeted second expert round. Он также последовательный по умолчанию и может использовать opt-in thread execution только для независимых вызовов выбранных ролей.
13. `REBALANCE`: обновить balance, brief и conflict.
14. `PLAN_CRITIQUE`: проверить план context-aware критиком с учётом `query_intake`, `must_address`, экспертных рисков и рекомендаций, conflict reports, dynamic roles, deliberation revisions, meta decision и предыдущего replan feedback. Stage 9 hardening добавляет совместимые поля `decision`, `ignored_risks`, `ignored_tradeoffs`, `ignored_must_address` и не позволяет молча принять план, который игнорирует критические экспертные риски или критические must-address пункты.
15. `REPLAN`: при `needs_revision` / `rejected` пересоздать только план на основе последнего контекста и actionable critique feedback.
16. `ANSWER` / `ANSWER_MODERATION`: использовать существующий `run_moderated_loop` как black-box компонент.
17. `FINALIZE` или `FAILED`: вернуть `final_answer`, `trace_report` и raw-данные.

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

`trace_report` содержит исходный и формализованный запрос, router decision, CMM mode, estimated cost class, routing warnings, parallel mode/max workers/parallelized stages, raw роли экспертов, `roles_used_unique`, экспертные раунды, dynamic role reports / roles used, deliberation rounds/revisions, balance reports, conflict reports, meta moderation decisions, plan, critique, moderation reports, JSON health diagnostics, approximate telemetry, revision count, confidence, warnings, state history, final state, transition count, iteration count и errors.

Для защиты и отладки есть `Lib.trace_formatter.format_trace_report(trace_report)`: он формирует компактный plain-text summary по маршруту, state path, ролям, balance/conflicts, deliberation, plan critique, answer moderation и warnings/errors без вывода больших raw JSON-структур.

`original_query` является источником истины. `formalized_query` заполняется из `cleaned_query` и используется только как вспомогательный текст; downstream-агенты также получают структурированный `query_intake`.

## Состав программных средств

- `main.py`: CLI-обертка.
- `Lib/orchestrator.py`: публичная обертка `run_cmm`.
- `Lib/state_machine.py`: bounded state-machine orchestration, история переходов и сбор trace/result.
- `Lib/state_fallbacks.py`: fallback-структуры для state machine.
- `Lib/state_trace.py`: компактные helpers для сборки result payload.
- `Lib/router.py`: deterministic routing layer для `DIRECT`, `LIGHT_CMM`, `FULL_CMM`.
- `Lib/direct_answer.py`: прямой low-cost ответ для простых low-risk задач.
- `Lib/parallel_utils.py`: bounded helpers для optional ordered thread execution независимых экспертных вызовов.
- `Lib/trace_formatter.py`: человекочитаемый summary поверх структурированного trace.
- `Lib/query_intake.py`: безопасный входной слой, который сохраняет `original_query` и извлекает `cleaned_query`, контекст, ограничения, критерии успеха, неизвестные и предпочтения.
- `Lib/json_retry.py`: общий retry helper для JSON-first model calls; при invalid JSON делает один repair-запрос и фиксирует `json_attempts` / warnings. Он используется intake, expert agents, role generation, planner, conflict analyzer, meta moderator, plan critic и answer moderator.
- `Lib/role_generator.py`: безопасная rules-first и template-based генерация дополнительных ролей из whitelist без model-generated system prompts.
- `Lib/expert_*`: роли, rules-first выбор ролей, экспертные вклады и панель. Экспертные JSON-вклады retry-ятся один раз, а при повторном сбое возвращают диагностический fallback contribution вместо немого пустого контекста.
- `Lib/expert_rounds.py`: выбор целевых ролей для второго экспертного раунда, запуск follow-up экспертов и объединение expert bundles.
- `Lib/balance_analyzer.py`: Balance Analyzer 2.0, который сохраняет tag/count checks и добавляет deterministic quality heuristics.
- `Lib/conflict_analyzer.py`: смысловой анализ согласий, разногласий, trade-offs, blind spots и рисков преждевременного консенсуса.
- `Lib/deliberation.py`: синтез экспертного brief.
- `Lib/deliberation_round.py`: структурированный раунд, где выбранные эксперты отвечают на позиции других ролей и пересматривают рекомендации; opt-in второй раунд ограничен named high-severity conflicts.
- `Lib/meta_moderator.py`: управление процессом.
- `Lib/plan_development.py`: JSON-first планировщик с retry, legacy text parser и context-aware fallback plan.
- `Lib/plan_critic.py`: context-aware JSON-first критик плана.
- `Lib/agent_moderator.py`: JSON-first модерация ответа и revision loop; финальный `REJECT` явно помечается и не должен восприниматься как обычный принятый ответ.
- `Lib/json_utils.py`: безопасный разбор JSON-like output.
- `cmm/eval.py`: evaluation harness.
- `tools/analyze_eval_routing.py`: построение `routing_analysis.csv` из eval `results.csv`.
- `tests/`: offline unit tests.

Legacy compatibility модули остаются импортируемыми, но не являются текущим основным pipeline: `Lib/Start_formalization.py` заменён в основном пути на `Lib/query_intake.py`, `Lib/agent_critic.py` и `Lib/critic_decision.py` совместимы со старым API вокруг `Lib/plan_critic.py`, а `Lib/Finish_agent.py` находится вне основного state-machine answer/moderation пути.

## Ожидаемые показатели

На текущем этапе не заявляется, что CMM стабильно лучше baseline. Ожидаемый показатель для MVP — воспроизводимая трассировка, безопасные fallback-и, прохождение offline-тестов и возможность сравнить baseline vs CMM на `cmm_dataset_v1.csv`.

Balance Analyzer 2.0 оценивает missing/dominant perspectives, perspective coverage, constraint coverage, stakeholder coverage, risk severity distribution, argument quality, dominance, blind spots и recommended balance action. Это эвристика, а не доказательство качества ответа.

Evaluation harness считает эвристические метрики покрытия:

- покрытие обязательных пунктов рубрики;
- покрытие ожидаемых перспектив;
- покрытие ожидаемых failure modes/рисков.

Эти метрики не являются научным доказательством качества и должны использоваться как regression/evaluation aid.

Real judged evaluation является отдельным opt-in режимом. Он формирует baseline-ответ и CMM-ответ, сохраняет trace CMM, строит blind Answer A/B пакет и либо экспортирует файл для человеческой оценки (`judge-mode none`), либо вызывает LLM judge (`judge-mode llm`). Рубрики и ожидаемые перспективы используются как критерии оценки судьи, а не как скрытое содержимое для генерации ответов.

## Источники

- Локальный датасет: `cmm_dataset_v1.csv`.
- Real-eval calibration dataset: `cmm_dataset_v2.csv`, 20 cases with `expected_mode`.
- Исходный код проекта: модули `Lib/` и `cmm/`.
- Локальные тесты: `tests/`.

## Ограничения

- Второй экспертный раунд есть, но он ограничен: он использует существующие базовые роли и whitelist dynamic role templates, и является targeted follow-up, а не свободной дискуссией.
- Structured deliberation round есть, но по умолчанию он ограничен одной schema-driven итерацией. Второй раунд opt-in, capped и запускается только для unresolved high-severity conflicts с определяемыми ролями; это не полноценная свободная debate/state-machine система.
- Dynamic roles ограничены заранее заданными шаблонами; модель может предложить только разрешенный key/tag, но не произвольный `system_prompt`.
- Role generation теперь rules-first: очевидные cost/measurement/legal/ethics роли выбираются без model call; модель используется только как дополнительный источник при свободных слотах и сложном контексте.
- Trace разделяет `dynamic_roles_generated`, `dynamic_roles_executed` и `dynamic_roles_rejected`; старое поле `dynamic_roles_used` сохранено как alias к реально выполненным `dynamic_roles_executed`.
- State machine является bounded MVP-оркестратором, а не бесконечным автономным процессом.
- Router является deterministic heuristic и может ошибочно выбрать слишком лёгкий или слишком тяжёлый путь; real eval следует анализировать по `cmm_mode` и router complexity.
- Eval v2 добавляет `expected_mode`, `actual_mode`, `router_mode_match`, `human_review.csv` и `routing_review.csv`; это помогает отделить ошибки маршрутизации от качества ответа.
- Context-aware plan critic проверяет план по ограничениям, экспертным рискам, unresolved trade-offs, dynamic-role concerns и deliberation revisions, но остаётся heuristic/model-assisted проверкой, а не формальной верификацией корректности.
- `REPLAN` не перезапускает весь экспертный pipeline; он пересоздаёт только план по последнему контексту и feedback критика.
- Query intake защищает исходный запрос от перезаписи, но сам по себе не доказывает повышение качества downstream-ответов.
- Нет fully free-form прямой дискуссии экспертов друг с другом.
- Есть opt-in thread-based запуск только независимых экспертных вызовов; shared state, transitions, routing, planning, critique, answer и moderation остаются последовательными.
- Evaluation harness остаётся последовательным на этом этапе, чтобы не менять порядок строк и semantics scoring.
- Нет произвольной генерации новых ролей; dynamic roles capped, whitelist-based и предназначены для missing expertise, blind spots, trade-offs, `ADD_EXPERT` / `DEEPEN`.
- Balance Analyzer 2.0 всё ещё является deterministic heuristic, а не доказательством качества или полноты экспертного анализа.
- Semantic conflict analysis помогает выявлять trade-offs и риски преждевременного консенсуса, а structured deliberation round помогает экспертам ответить на позиции друг друга, но это всё ещё ограниченный MVP-механизм.
- Нет UI.
- Реальные LLM-вызовы зависят от API-ключа и внешней доступности модели.
- Mock evaluation не является доказательством качества или реальным сравнением моделей.
- Real judged evaluation даёт только первые ограниченные evidence по выборке и не является доказательством универсального превосходства CMM.
