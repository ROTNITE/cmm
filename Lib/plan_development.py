# agent_planner.py - планировщик

import json
from datetime import datetime
from typing import Any

from Lib.config import get_stage_settings
from Lib.json_retry import call_json_model
from Lib.json_utils import to_string_list


_GENERIC_STEP_MARKERS = (
    "assess",
    "evaluate",
    "analyze",
    "develop",
    "design",
    "implement",
    "launch",
    "monitor",
    "review",
    "определ",
    "оцен",
    "анализ",
    "разработ",
    "внедр",
    "запуск",
    "монитор",
    "пересмотр",
)


def _context_items(context, section, key, max_items=5):
    if not isinstance(context, dict):
        return []
    source = context.get(section) if isinstance(context.get(section), dict) else {}
    return to_string_list(source.get(key), max_items=max_items)


def _context_dict_items(context, section, key, max_items=8):
    if not isinstance(context, dict):
        return []
    source = context.get(section) if isinstance(context.get(section), dict) else {}
    values = source.get(key)
    out = []
    for item in values if isinstance(values, list) else []:
        if isinstance(item, dict):
            out.append(dict(item))
        if len(out) >= max_items:
            break
    return out


def _dedupe_strings(items, max_items=12):
    out = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        text = str(item or "").strip()
        marker = text.lower()
        if not text or marker in seen:
            continue
        seen.add(marker)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _step_dict(
    number: int,
    title: str,
    *,
    substeps=None,
    uses=None,
    covers_constraints=None,
    covers_success=None,
    mitigates_risks=None,
    handles_tradeoffs=None,
    serves_stakeholders=None,
):
    return {
        "number": str(number),
        "title": title,
        "substeps": _dedupe_strings(list(substeps or []), max_items=8),
        "uses_expert_inputs": _dedupe_strings(list(uses or []), max_items=8),
        "covers_constraints": _dedupe_strings(list(covers_constraints or []), max_items=8),
        "covers_success_criteria": _dedupe_strings(list(covers_success or []), max_items=8),
        "mitigates_risks": _dedupe_strings(list(mitigates_risks or []), max_items=8),
        "handles_tradeoffs": _dedupe_strings(list(handles_tradeoffs or []), max_items=8),
        "serves_stakeholders": _dedupe_strings(list(serves_stakeholders or []), max_items=8),
    }


def _stakeholder_items(context, max_items=8):
    values = []
    for section in ("balance_report", "deliberation_brief"):
        source = context.get(section) if isinstance(context, dict) and isinstance(context.get(section), dict) else {}
        raw_items = source.get("stakeholder_coverage")
        for item in raw_items if isinstance(raw_items, list) else []:
            if isinstance(item, dict):
                stakeholder = str(item.get("stakeholder") or "").strip()
            else:
                stakeholder = str(item or "").strip()
            if stakeholder:
                values.append(stakeholder)
    return _dedupe_strings(values, max_items=max_items)


def _must_address_items(context, max_items=12):
    return _context_items(context, "deliberation_brief", "must_address", max_items)


def _coverage_type_for_item(item: str, *, constraints, success, risks, tradeoffs, stakeholders) -> str:
    lowered = str(item or "").strip().lower()
    if not lowered:
        return "risk"
    for value in constraints:
        if lowered == str(value or "").strip().lower():
            return "constraint"
    for value in success:
        if lowered == str(value or "").strip().lower():
            return "success_criterion"
    for value in tradeoffs:
        if lowered == str(value or "").strip().lower():
            return "tradeoff"
    for value in stakeholders:
        if lowered == str(value or "").strip().lower():
            return "stakeholder"
    return "risk"


def _step_text(step: dict) -> str:
    if not isinstance(step, dict):
        return ""
    parts = [
        str(step.get("title") or ""),
        *[str(item) for item in step.get("substeps") or []],
        *[str(item) for item in step.get("uses_expert_inputs") or []],
        *[str(item) for item in step.get("covers_constraints") or []],
        *[str(item) for item in step.get("covers_success_criteria") or []],
        *[str(item) for item in step.get("mitigates_risks") or []],
        *[str(item) for item in step.get("handles_tradeoffs") or []],
        *[str(item) for item in step.get("serves_stakeholders") or []],
    ]
    return json.dumps(parts, ensure_ascii=False).lower()


def _covered_step_numbers(plan: dict | None, item: str, explicit_field: str) -> list[str]:
    out = []
    lowered = str(item or "").strip().lower()
    for step in (plan or {}).get("steps") if isinstance((plan or {}).get("steps"), list) else []:
        if not isinstance(step, dict):
            continue
        step_number = str(step.get("number") or "").strip()
        explicit_values = [str(value).strip().lower() for value in step.get(explicit_field) or [] if str(value).strip()]
        if lowered and lowered in explicit_values:
            if step_number:
                out.append(step_number)
            continue
        if lowered and lowered in _step_text(step):
            if step_number:
                out.append(step_number)
    return out


def _is_generic_title(title: str) -> bool:
    lowered = str(title or "").strip().lower()
    return bool(lowered) and any(marker in lowered for marker in _GENERIC_STEP_MARKERS)


def _step_has_linkage(step: dict) -> bool:
    if not isinstance(step, dict):
        return False
    return any(
        bool(step.get(key))
        for key in (
            "uses_expert_inputs",
            "covers_constraints",
            "covers_success_criteria",
            "mitigates_risks",
            "handles_tradeoffs",
            "serves_stakeholders",
        )
    )


def _requires_context_carrying_plan(context: dict | None) -> bool:
    if not isinstance(context, dict):
        return False
    count = 0
    count += len(_context_items(context, "query_intake", "constraints", 10))
    count += len(_context_items(context, "query_intake", "success_criteria", 8))
    count += len(_context_items(context, "deliberation_brief", "expert_risks", 10))
    count += len(_must_address_items(context, 12))
    count += len(_tradeoff_items(context, 8))
    count += len(_stakeholder_items(context, 8))
    return count >= 3


def _plan_has_context_linkage(plan: dict | None) -> bool:
    if not isinstance(plan, dict):
        return False
    if plan.get("must_address_mapping") or plan.get("stakeholder_coverage"):
        return True
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    return any(_step_has_linkage(step) for step in steps if isinstance(step, dict))


def _mapping_coverage_count(items: list[dict] | None) -> int:
    count = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        covered = item.get("covered_in_steps")
        if isinstance(covered, list) and any(str(value).strip() for value in covered):
            count += 1
    return count


def _plan_has_meaningful_context_coverage(plan: dict | None, context: dict | None) -> bool:
    if not isinstance(plan, dict):
        return False
    if not _requires_context_carrying_plan(context):
        return True

    summary = _coverage_summary_from_context(context, plan)
    must_address = summary.get("must_address_mapping", [])
    stakeholder_coverage = summary.get("stakeholder_coverage", [])
    covered_must_address = _mapping_coverage_count(must_address)
    covered_stakeholders = _mapping_coverage_count(stakeholder_coverage)
    risks = summary.get("risks_mitigated", [])
    tradeoffs = summary.get("tradeoffs_handled", [])
    constraints = summary.get("constraints_covered", [])
    success = summary.get("success_criteria_covered", [])

    failures = 0
    if len(must_address) >= 3 and covered_must_address < min(2, len(must_address)):
        failures += 1
    if stakeholder_coverage and covered_stakeholders == 0:
        failures += 1
    if _context_items(context, "deliberation_brief", "expert_risks", 8) and not risks:
        failures += 1
    if _tradeoff_items(context, 6) and not tradeoffs:
        failures += 1
    if _context_items(context, "query_intake", "constraints", 8) and not constraints:
        failures += 1
    if _context_items(context, "query_intake", "success_criteria", 8) and not success:
        failures += 1
    return failures == 0


def _fallback_steps(context):
    constraints = _context_items(context, "query_intake", "constraints", 5)
    success_criteria = _context_items(context, "query_intake", "success_criteria", 5)
    must_address = _context_items(context, "deliberation_brief", "must_address", 5)
    risks = _context_items(context, "deliberation_brief", "expert_risks", 6)
    blind_spots = _context_items(context, "conflict_report", "blind_spots", 5)
    tradeoffs = _context_items(context, "conflict_report", "unresolved_tradeoffs", 5)
    stakeholders = _stakeholder_items(context, 6)

    steps = []
    steps.append(
        _step_dict(
            len(steps) + 1,
            "Сформулировать решение вокруг цели запроса и критериев качества",
            substeps=_dedupe_strings(success_criteria or must_address or blind_spots, max_items=6),
            uses=success_criteria[:4] + must_address[:4],
            covers_success=success_criteria[:4],
        )
    )
    if constraints:
        steps.append(
            _step_dict(
                len(steps) + 1,
                "Встроить ограничения в рабочий план и критерии выбора",
                substeps=constraints,
                uses=constraints,
                covers_constraints=constraints,
            )
        )
    if must_address or blind_spots or tradeoffs or risks:
        items = must_address + blind_spots + [str(item) for item in tradeoffs] + risks
        steps.append(
            _step_dict(
                len(steps) + 1,
                "Закрыть обязательные риски, blind spots и trade-offs",
                substeps=items[:8],
                uses=items[:8],
                mitigates_risks=risks[:6] + blind_spots[:4],
                handles_tradeoffs=[str(item) for item in tradeoffs][:6],
            )
        )
    if stakeholders:
        steps.append(
            _step_dict(
                len(steps) + 1,
                "Показать, как решение учитывает заинтересованные стороны",
                substeps=stakeholders,
                uses=stakeholders,
                serves_stakeholders=stakeholders,
            )
        )
    steps.append(
        _step_dict(
            len(steps) + 1,
            "Подготовить итоговый ответ с реалистичными шагами, caveats и проверкой эффекта",
            substeps=_dedupe_strings(success_criteria + tradeoffs + risks, max_items=6),
            uses=_dedupe_strings(success_criteria + risks + must_address, max_items=6),
            covers_success=success_criteria[:4],
            mitigates_risks=risks[:4],
            handles_tradeoffs=[str(item) for item in tradeoffs][:4],
        )
    )
    return steps


def _repair_plan_linkage(plan: dict, context: dict | None) -> dict:
    """Repair plan by adding missing linkage to context items.

    When planner generates structurally valid but semantically weak plan,
    this function infers linkage from step text and adds explicit coverage.
    """
    if not isinstance(plan, dict) or not isinstance(context, dict):
        return plan

    constraints = _context_items(context, "query_intake", "constraints", 10)
    success = _context_items(context, "query_intake", "success_criteria", 10)
    risks = _context_items(context, "deliberation_brief", "expert_risks", 10)
    tradeoffs = _tradeoff_items(context, 8)
    stakeholders = _stakeholder_items(context, 10)
    must_address = _must_address_items(context, 14)

    # Repair each step by inferring linkage from step text
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue

        step_text = _step_text(step).lower()

        # Infer constraint coverage
        if not step.get("covers_constraints"):
            step["covers_constraints"] = [
                c for c in constraints if c.lower() in step_text
            ][:6]

        # Infer success criteria coverage
        if not step.get("covers_success_criteria"):
            step["covers_success_criteria"] = [
                s for s in success if s.lower() in step_text
            ][:6]

        # Infer risk mitigation
        if not step.get("mitigates_risks"):
            step["mitigates_risks"] = [
                r for r in risks if r.lower() in step_text
            ][:6]

        # Infer tradeoff handling
        if not step.get("handles_tradeoffs"):
            step["handles_tradeoffs"] = [
                t for t in tradeoffs if t.lower() in step_text
            ][:6]

        # Infer stakeholder serving
        if not step.get("serves_stakeholders"):
            step["serves_stakeholders"] = [
                s for s in stakeholders if s.lower() in step_text
            ][:6]

        # Infer expert input usage from must_address
        if not step.get("uses_expert_inputs"):
            step["uses_expert_inputs"] = [
                m for m in must_address if m.lower() in step_text
            ][:6]

    # Recompute coverage summary with repaired plan
    summary = _coverage_summary_from_context(context, plan)
    plan["constraints_covered"] = summary.get("constraints_covered", [])
    plan["success_criteria_covered"] = summary.get("success_criteria_covered", [])
    plan["risks_mitigated"] = summary.get("risks_mitigated", [])
    plan["tradeoffs_handled"] = summary.get("tradeoffs_handled", [])
    plan["stakeholder_coverage"] = summary.get("stakeholder_coverage", [])
    plan["must_address_mapping"] = summary.get("must_address_mapping", [])

    return plan


def _tradeoff_items(context, max_items=6):
    if not isinstance(context, dict):
        return []
    source = context.get("conflict_report") if isinstance(context.get("conflict_report"), dict) else {}
    items = []
    for tradeoff in source.get("unresolved_tradeoffs", []) or []:
        if isinstance(tradeoff, dict):
            value = tradeoff.get("tradeoff") or tradeoff.get("why_it_matters")
        else:
            value = tradeoff
        if isinstance(value, str) and value.strip():
            items.append(value.strip())
        if len(items) >= max_items:
            break
    return items


def _covered_items(items: list[str], text: str, max_items: int = 8) -> list[str]:
    lowered = str(text or "").lower()
    covered = []
    for item in items:
        candidate = str(item or "").strip()
        if candidate and candidate.lower() in lowered:
            covered.append(candidate)
        if len(covered) >= max_items:
            break
    return covered


def _coverage_summary_from_context(context: dict | None, plan: dict | None = None) -> dict[str, list[str]]:
    source_text = json.dumps(plan or context or {}, ensure_ascii=False).lower() if isinstance(plan, dict) else json.dumps(context or {}, ensure_ascii=False).lower()
    constraints = _context_items(context, "query_intake", "constraints", 8)
    success = _context_items(context, "query_intake", "success_criteria", 8)
    risks = _context_items(context, "deliberation_brief", "expert_risks", 8)
    tradeoffs = _tradeoff_items(context, 8)
    stakeholders = _stakeholder_items(context, 8)
    must_address = _must_address_items(context, 12)
    stakeholder_coverage = [
        {"stakeholder": item, "covered_in_steps": _covered_step_numbers(plan or {}, item, "serves_stakeholders")}
        for item in stakeholders
    ]
    must_address_mapping = []
    for item in must_address:
        coverage_type = _coverage_type_for_item(
            item,
            constraints=constraints,
            success=success,
            risks=risks,
            tradeoffs=tradeoffs,
            stakeholders=stakeholders,
        )
        field = {
            "constraint": "covers_constraints",
            "success_criterion": "covers_success_criteria",
            "risk": "mitigates_risks",
            "tradeoff": "handles_tradeoffs",
            "stakeholder": "serves_stakeholders",
        }.get(coverage_type, "uses_expert_inputs")
        must_address_mapping.append(
            {
                "item": item,
                "covered_in_steps": _covered_step_numbers(plan or {}, item, field),
                "coverage_type": coverage_type,
            }
        )
    return {
        "constraints_covered": _covered_items(constraints, source_text, 8),
        "success_criteria_covered": _covered_items(success, source_text, 8),
        "risks_mitigated": _covered_items(risks, source_text, 8),
        "tradeoffs_handled": _covered_items(tradeoffs, source_text, 8),
        "stakeholder_coverage": stakeholder_coverage,
        "must_address_mapping": must_address_mapping,
    }


def _fallback_plan(
    query,
    depth="detailed",
    warning="model_response_unavailable",
    *,
    context=None,
    extra_warnings=None,
    json_attempts=0,
):
    fallback = {
        "query": query,
        "main_idea": f"Ответить на: {query}",
        "preparation": [],
        "steps": _fallback_steps(context),
        "nuances": [],
        "potential_problems": _context_items(context, "deliberation_brief", "expert_risks", 6)
        + _context_items(context, "conflict_report", "blind_spots", 6),
        "result": "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": [warning] + list(extra_warnings or []),
        "json_attempts": int(json_attempts or 0),
        "raw_format": "fallback",
        "source": "fallback",
    }
    fallback.update(_coverage_summary_from_context(context, fallback))
    return fallback


def _normalize_step(item, index):
    if not isinstance(item, dict):
        return None

    number = item.get("number")
    if not isinstance(number, str) or not number.strip():
        number = str(index)

    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    return {
        "number": number.strip(),
        "title": title.strip(),
        "substeps": to_string_list(item.get("substeps"), max_items=8),
        "uses_expert_inputs": to_string_list(item.get("uses_expert_inputs"), max_items=8),
        "covers_constraints": to_string_list(item.get("covers_constraints"), max_items=8),
        "covers_success_criteria": to_string_list(item.get("covers_success_criteria"), max_items=8),
        "mitigates_risks": to_string_list(item.get("mitigates_risks"), max_items=8),
        "handles_tradeoffs": to_string_list(item.get("handles_tradeoffs"), max_items=8),
        "serves_stakeholders": to_string_list(item.get("serves_stakeholders"), max_items=8),
    }


def _normalize_mapping_items(value, item_key, max_items=12):
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        main = str(item.get(item_key) or "").strip()
        if not main:
            continue
        covered = [str(v).strip() for v in item.get("covered_in_steps") or [] if str(v).strip()]
        normalized = {item_key: main, "covered_in_steps": covered}
        if item_key == "item":
            coverage_type = str(item.get("coverage_type") or "").strip() or "risk"
            normalized["coverage_type"] = coverage_type
        out.append(normalized)
        if len(out) >= max_items:
            break
    return out


def _normalize_json_plan(payload, query, depth, *, context=None):
    if not isinstance(payload, dict):
        return None

    steps_raw = payload.get("steps")
    steps = []
    if isinstance(steps_raw, list):
        for index, item in enumerate(steps_raw, start=1):
            step = _normalize_step(item, index)
            if step:
                steps.append(step)

    main_idea = payload.get("main_idea")
    result = payload.get("result")

    plan = {
        "query": query,
        "main_idea": main_idea.strip() if isinstance(main_idea, str) else "",
        "preparation": to_string_list(payload.get("preparation"), max_items=10),
        "steps": steps,
        "nuances": to_string_list(payload.get("nuances"), max_items=10),
        "potential_problems": to_string_list(payload.get("potential_problems"), max_items=10),
        "result": result.strip() if isinstance(result, str) else "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": [],
        "raw_format": "json",
        "constraints_covered": to_string_list(payload.get("constraints_covered"), max_items=10),
        "success_criteria_covered": to_string_list(payload.get("success_criteria_covered"), max_items=10),
        "risks_mitigated": to_string_list(payload.get("risks_mitigated"), max_items=10),
        "tradeoffs_handled": to_string_list(payload.get("tradeoffs_handled"), max_items=10),
        "stakeholder_coverage": _normalize_mapping_items(payload.get("stakeholder_coverage"), "stakeholder", 10),
        "must_address_mapping": _normalize_mapping_items(payload.get("must_address_mapping"), "item", 14),
    }

    if not plan["main_idea"] and not plan["steps"]:
        return None

    summary = _coverage_summary_from_context(context, plan)
    for key in ("constraints_covered", "success_criteria_covered", "risks_mitigated", "tradeoffs_handled"):
        if not plan.get(key):
            plan[key] = summary.get(key, [])
    if not plan.get("stakeholder_coverage"):
        plan["stakeholder_coverage"] = summary.get("stakeholder_coverage", [])
    if not plan.get("must_address_mapping"):
        plan["must_address_mapping"] = summary.get("must_address_mapping", [])

    if _requires_context_carrying_plan(context):
        has_linkage = _plan_has_context_linkage(plan)
        generic_titles = [
            step.get("title")
            for step in plan["steps"]
            if isinstance(step, dict) and _is_generic_title(step.get("title", ""))
        ]
        has_meaningful_coverage = _plan_has_meaningful_context_coverage(plan, context)

        # CRITICAL FIX: Don't reject plan, instead repair it with structured fallback
        if (
            not has_linkage
            or (generic_titles and len(generic_titles) == len(plan["steps"]))
            or not has_meaningful_coverage
        ):
            # Add warning but keep the plan structure
            plan["parse_warnings"].append("plan_lacks_semantic_linkage_to_context")

            # Repair: Add missing linkage by inferring from context
            plan = _repair_plan_linkage(plan, context)

    return plan


def _parse_legacy_text_plan(response, query, depth, context=None):
    plan = {
        "query": query,
        "main_idea": "",
        "preparation": [],
        "steps": [],
        "nuances": [],
        "potential_problems": [],
        "result": "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": ["json_parse_failed; used legacy text parser"],
        "json_attempts": 0,
        "raw_format": "legacy_text",
        "source": "legacy_text",
        "constraints_covered": [],
        "success_criteria_covered": [],
        "risks_mitigated": [],
        "tradeoffs_handled": [],
        "stakeholder_coverage": [],
        "must_address_mapping": [],
    }

    current_section = ""
    current_step = None

    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "ОСНОВНАЯ ИДЕЯ" in line.upper():
            current_section = "main_idea"
            if ":" in line:
                plan["main_idea"] = line.split(":", 1)[1].strip()
        elif "ПОДГОТОВКА" in line.upper():
            current_section = "preparation"
        elif "ШАГИ" in line.upper():
            current_section = "steps"
        elif "НЮАНСЫ" in line.upper():
            current_section = "nuances"
        elif "РЕЗУЛЬТАТ" in line.upper():
            current_section = "result"
        else:
            if current_section == "main_idea" and not plan["main_idea"]:
                plan["main_idea"] = line
            elif current_section == "preparation" and line.startswith("-"):
                plan["preparation"].append(line.lstrip("- "))
            elif current_section == "steps":
                if line[0].isdigit() and "." in line:
                    if current_step:
                        plan["steps"].append(current_step)
                    parts = line.split(".", 1)
                    current_step = {
                        "number": parts[0],
                        "title": parts[1].strip(),
                        "substeps": [],
                        "uses_expert_inputs": [],
                    }
                elif line.startswith("-") and current_step:
                    current_step["substeps"].append(line.lstrip("- "))
            elif current_section == "nuances" and line.startswith("-"):
                plan["nuances"].append(line.lstrip("- "))
            elif current_section == "result" and not plan["result"]:
                plan["result"] = line

    if current_step and current_step not in plan["steps"]:
        plan["steps"].append(current_step)

    if not plan["main_idea"] and not plan["steps"]:
        return _fallback_plan(
            query,
            depth=depth,
            warning="json_and_legacy_plan_parse_failed",
            context=context,
        )

    plan.update(_coverage_summary_from_context(context, plan))
    return plan


def _replan_feedback_items(context, max_items=8):
    if not isinstance(context, dict):
        return []

    replan = context.get("replan_context") if isinstance(context.get("replan_context"), dict) else {}
    critique = replan.get("plan_critique") if isinstance(replan.get("plan_critique"), dict) else {}

    items = []
    for key in (
        "feedback",
        "critical_blockers",
        "ignored_must_address",
        "ignored_risks",
        "ignored_tradeoffs",
        "ignored_expert_risks",
        "unresolved_tradeoffs",
    ):
        source = replan.get(key)
        if source is None:
            source = critique.get(key)
        items.extend(to_string_list(source, max_items=max_items))

    deduped = []
    seen = set()
    for item in items:
        marker = item.strip().lower()
        if marker and marker not in seen:
            seen.add(marker)
            deduped.append(item.strip())
        if len(deduped) >= max_items:
            break
    return deduped


def _previous_plan_from_context(context):
    if not isinstance(context, dict):
        return {}
    replan = context.get("replan_context") if isinstance(context.get("replan_context"), dict) else {}
    previous = replan.get("previous_plan")
    return previous if isinstance(previous, dict) else {}


def _repair_previous_plan_fallback(
    query,
    depth="detailed",
    *,
    context=None,
    extra_warnings=None,
    json_attempts=0,
):
    """Repair previous valid plan instead of replacing it with generic fallback."""
    previous = _previous_plan_from_context(context)
    if not isinstance(previous, dict) or not previous.get("steps"):
        return None

    plan = {
        "query": query,
        "main_idea": previous.get("main_idea") or f"Ответить на: {query}",
        "preparation": to_string_list(previous.get("preparation"), max_items=10),
        "steps": [],
        "nuances": to_string_list(previous.get("nuances"), max_items=10),
        "potential_problems": to_string_list(previous.get("potential_problems"), max_items=10),
        "result": previous.get("result") if isinstance(previous.get("result"), str) else "",
        "timestamp": str(datetime.now()),
        "depth": depth,
        "parse_warnings": ["json_replan_failed_used_previous_plan_repair"] + list(extra_warnings or []),
        "json_attempts": int(json_attempts or 0),
        "raw_format": "fallback_repair",
        "source": "fallback_repair",
        "constraints_covered": to_string_list(previous.get("constraints_covered"), max_items=10),
        "success_criteria_covered": to_string_list(previous.get("success_criteria_covered"), max_items=10),
        "risks_mitigated": to_string_list(previous.get("risks_mitigated"), max_items=10),
        "tradeoffs_handled": to_string_list(previous.get("tradeoffs_handled"), max_items=10),
        "stakeholder_coverage": list(previous.get("stakeholder_coverage") or []),
        "must_address_mapping": list(previous.get("must_address_mapping") or []),
    }

    for index, item in enumerate(previous.get("steps") or [], start=1):
        step = _normalize_step(item, index)
        if step:
            plan["steps"].append(step)

    replan_context = context.get("replan_context", {}) if isinstance(context, dict) and isinstance(context.get("replan_context"), dict) else {}
    feedback_items = _replan_feedback_items(context, max_items=8)
    missing_constraints = to_string_list(replan_context.get("missing_constraints"), max_items=6)
    ignored_success = to_string_list(replan_context.get("ignored_success_criteria"), max_items=6)
    ignored_must_address = to_string_list(replan_context.get("ignored_must_address"), max_items=6)
    ignored_risks = to_string_list(replan_context.get("ignored_risks"), max_items=6)
    ignored_tradeoffs = to_string_list(replan_context.get("ignored_tradeoffs"), max_items=6)
    stakeholder_gaps = [
        item.get("stakeholder")
        for item in _coverage_summary_from_context(context, previous).get("stakeholder_coverage", [])
        if isinstance(item, dict) and not item.get("covered_in_steps") and isinstance(item.get("stakeholder"), str)
    ][:6]

    if missing_constraints or ignored_success:
        focused = _dedupe_strings(missing_constraints + ignored_success, max_items=8)
        plan["steps"].append(
            _step_dict(
                len(plan["steps"]) + 1,
                "Явно встроить незакрытые ограничения и критерии успеха",
                substeps=focused,
                uses=focused,
                covers_constraints=missing_constraints[:6],
                covers_success=ignored_success[:6],
            )
        )

    if ignored_must_address or ignored_risks or ignored_tradeoffs:
        focused = _dedupe_strings(
            ignored_must_address + ignored_risks + ignored_tradeoffs,
            max_items=10,
        )
        plan["steps"].append(
            _step_dict(
                len(plan["steps"]) + 1,
                "Закрыть незакрытые must-address пункты, риски и trade-offs",
                substeps=focused,
                uses=focused,
                mitigates_risks=ignored_risks[:6],
                handles_tradeoffs=ignored_tradeoffs[:6],
            )
        )

    if stakeholder_gaps:
        plan["steps"].append(
            _step_dict(
                len(plan["steps"]) + 1,
                "Явно учесть интересы незакрытых заинтересованных сторон",
                substeps=stakeholder_gaps,
                uses=stakeholder_gaps,
                serves_stakeholders=stakeholder_gaps,
            )
        )

    if feedback_items:
        plan["steps"].append(
            _step_dict(
                len(plan["steps"]) + 1,
                "Закрыть замечания критика перед финальным ответом",
                substeps=feedback_items,
                uses=feedback_items,
                covers_constraints=_context_items(context, "query_intake", "constraints", 6),
                covers_success=_context_items(context, "query_intake", "success_criteria", 6),
                mitigates_risks=_context_items(context, "deliberation_brief", "expert_risks", 6),
                handles_tradeoffs=_tradeoff_items(context, 6),
                serves_stakeholders=_stakeholder_items(context, 6),
            )
        )

    risks = _context_items(context, "deliberation_brief", "expert_risks", 6)
    for risk in risks:
        if risk not in plan["potential_problems"]:
            plan["potential_problems"].append(risk)

    if not plan["result"]:
        plan["result"] = "Итоговый ответ должен учитывать ограничения, риски, trade-offs и метрики проверки эффекта."

    plan.update(_coverage_summary_from_context(context, plan))
    return plan


def develop_plan(query, context=None, depth="detailed", model="deepseek-chat"):
    """
    Создаёт план ответа на запрос.

    query - вопрос пользователя
    context - дополнительная информация (необязательно)
    depth - глубина плана: "quick", "detailed", "comprehensive"
    model - model name forwarded to the configured AI provider
    """

    # Проверяем, что запрос не пустой
    if not query:
        return {"error": "Пустой запрос"}

    # Настройки для разной глубины плана
    stage_defaults = get_stage_settings("planner", {"tokens": 1500, "temp": 0.3})
    settings = {
        "quick": {"tokens": min(800, int(stage_defaults.get("tokens") or 1500)), "temp": float(stage_defaults.get("temp") or 0.3)},
        "detailed": {"tokens": int(stage_defaults.get("tokens") or 1500), "temp": float(stage_defaults.get("temp") or 0.3)},
        "comprehensive": {"tokens": max(1200, int(stage_defaults.get("tokens") or 1500)), "temp": max(0.2, float(stage_defaults.get("temp") or 0.3))}
    }

    # Берём настройки для нужной глубины, если нет - используем detailed
    current = settings.get(depth, settings["detailed"])

    system_prompt = """You are a planning assistant for Collective Meta-Moderation.
Create a concrete, context-carrying plan for answering the user's query.
Original query is authoritative.
Return one valid JSON object only. No markdown. No prose.

Rules:
- Do not return generic outline steps.
- Every step must connect to real CMM context through uses_expert_inputs or coverage arrays.
- Use must_address, risks, trade-offs, stakeholders, constraints, and success criteria explicitly.
- If this is a replan, fix the critique omissions instead of repeating the previous outline.

Schema:
{
  "main_idea": "string - the core answer strategy",
  "preparation": ["string"],
  "steps": [
    {
      "number": "1",
      "title": "string - specific actionable step title",
      "substeps": ["string - concrete actions or checks"],
      "uses_expert_inputs": ["string - expert recommendation, risk, question, or must-address item"],
      "covers_constraints": ["string"],
      "covers_success_criteria": ["string"],
      "mitigates_risks": ["string"],
      "handles_tradeoffs": ["string"],
      "serves_stakeholders": ["string"]
    }
  ],
  "nuances": ["string"],
  "potential_problems": ["string"],
  "result": "string",
  "constraints_covered": ["string"],
  "success_criteria_covered": ["string"],
  "risks_mitigated": ["string"],
  "tradeoffs_handled": ["string"],
  "stakeholder_coverage": [{"stakeholder": "string", "covered_in_steps": ["1", "2"]}],
  "must_address_mapping": [{"item": "string", "covered_in_steps": ["1"], "coverage_type": "constraint|risk|tradeoff|stakeholder|success_criterion"}]
}
"""

    planner_packet = {
        "query": query,
        "query_intake": context.get("query_intake", {}) if isinstance(context, dict) else {},
        "deliberation_brief": {
            "must_address": _must_address_items(context, 12),
            "expert_recommendations": _context_items(context, "deliberation_brief", "expert_recommendations", 10),
            "expert_risks": _context_items(context, "deliberation_brief", "expert_risks", 10),
            "balance_notes": _context_items(context, "deliberation_brief", "balance_notes", 6),
            "stakeholder_coverage": _context_dict_items(context, "deliberation_brief", "stakeholder_coverage", 8),
        },
        "conflict_report": {
            "unresolved_tradeoffs": _tradeoff_items(context, 8),
            "blind_spots": _context_items(context, "conflict_report", "blind_spots", 8),
            "premature_consensus_risks": _context_items(context, "conflict_report", "premature_consensus_risks", 8),
        },
        "balance_report": {
            "missing_perspectives": _context_items(context, "balance_report", "missing_perspectives", 8),
            "blind_spots": _context_items(context, "balance_report", "blind_spots", 8),
            "stakeholder_coverage": _context_dict_items(context, "balance_report", "stakeholder_coverage", 8),
            "recommended_action": (
                context.get("balance_report", {}).get("recommended_action")
                if isinstance(context, dict) and isinstance(context.get("balance_report"), dict)
                else ""
            ),
        },
        "replan_context": context.get("replan_context", {}) if isinstance(context, dict) else {},
        "previous_plan": _previous_plan_from_context(context),
    }

    user_prompt = (
        "Build a context-carrying answer plan for this query. "
        "Use every substantive must-address item, risk, trade-off, and stakeholder when relevant.\n"
        + json.dumps(planner_packet, ensure_ascii=False)
    )

    result = call_json_model(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=current["temp"],
        tokens=current["tokens"],
        model=model,
        max_retries=1,
        log_purpose="planner",
    )

    payload = result.get("payload") if isinstance(result, dict) else None
    warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    plan = _normalize_json_plan(payload, query=query, depth=depth, context=context)
    if plan is not None:
        plan["parse_warnings"] = warnings
        plan["json_attempts"] = attempts
        plan["source"] = "model"
        summary = _coverage_summary_from_context(context, plan)
        for key, value in summary.items():
            if not plan.get(key):
                plan[key] = value
        return plan

    repair_plan = _repair_previous_plan_fallback(
        query,
        depth=depth,
        context=context,
        extra_warnings=warnings,
        json_attempts=attempts,
    )
    if repair_plan is not None:
        return repair_plan

    plan = _parse_legacy_text_plan(raw, query=query, depth=depth, context=context)
    plan["parse_warnings"] = list(plan.get("parse_warnings", [])) + warnings
    plan["json_attempts"] = attempts
    if plan.get("raw_format") == "fallback":
        plan["source"] = "fallback"

    return plan

def show_plan(plan):
    """Manual display helper for local scripts."""
    print("\n" + "="*50)
    print("📋 ПЛАН")
    print("="*50)

    if plan.get("main_idea"):
        print(f"\n🎯 ИДЕЯ: {plan['main_idea']}")

    if plan.get("preparation"):
        print("\n📦 ПОДГОТОВКА:")
        for item in plan["preparation"]:
            print(f"  • {item}")

    if plan.get("steps"):
        print("\n📝 ШАГИ:")
        for step in plan["steps"]:
            print(f"\n  {step['number']}. {step['title']}")
            for substep in step.get("substeps", []):
                print(f"     • {substep}")

    if plan.get("nuances"):
        print("\n⚠️ НЮАНСЫ:")
        for item in plan["nuances"]:
            print(f"  • {item}")

    if plan.get("result"):
        print(f"\n✨ РЕЗУЛЬТАТ: {plan['result']}")

    print("\n" + "="*50)

# Простой способ использовать планировщик
if __name__ == "__main__":
    # Тестовые запросы
    tests = [
        "Как научиться программировать?",
        "Что лучше: Python или JavaScript?"
    ]

    for test in tests:
        print(f"\n\n📝 Тест: {test}")
        plan = develop_plan(test, depth="quick")
        show_plan(plan)
        input("\nНажми Enter для следующего теста...")
