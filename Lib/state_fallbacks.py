"""Fallback structures for the bounded CMM state machine."""

from __future__ import annotations


def empty_expert_bundle() -> dict:
    return {
        "roles": [],
        "contributions": [],
        "synthesis": {
            "recommendations": [],
            "risks": [],
            "questions": [],
            "perspective_counts": {},
        },
    }


def conservative_balance_report() -> dict:
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": ["strategy", "engineering", "risk", "user"],
        "notes": ["Balance analysis failed; conservative fallback marks all base perspectives as missing."],
        "perspective_coverage": {
            "strategy": 0.0,
            "engineering": 0.0,
            "risk": 0.0,
            "user": 0.0,
        },
        "stakeholder_coverage": [],
        "constraint_coverage": [],
        "risk_severity_distribution": {"low": 0, "medium": 0, "high": 0, "unknown": 0},
        "argument_quality": {
            "evidence_level": 0.0,
            "specificity": 0.0,
            "actionability": 0.0,
            "novelty": 0.0,
            "tradeoff_awareness": 0.0,
        },
        "dominance": {
            "dominant_perspective": None,
            "dominant_ratio": 0.0,
            "counts": {},
            "total_contributions": 0,
        },
        "blind_spots": [
            "Missing base perspective: strategy.",
            "Missing base perspective: engineering.",
            "Missing base perspective: risk.",
            "Missing base perspective: user.",
        ],
        "recommended_action": "ADD_EXPERT",
    }


def empty_deliberation_brief(query: str) -> dict:
    return {
        "summary": f"Expert deliberation for query: {query[:240]}",
        "expert_recommendations": [],
        "expert_risks": [],
        "expert_questions": [],
        "perspective_counts": {},
        "missing_perspectives": [],
        "dominant_perspective_found": False,
        "balance_notes": [],
        "must_address": [],
    }


def fallback_query_intake(original_query: str, warning: str) -> dict:
    cleaned_query = str(original_query or "").strip()
    complexity = "simple" if len(cleaned_query.split()) <= 12 else "moderate"
    return {
        "original_query": original_query,
        "cleaned_query": cleaned_query or original_query,
        "task_goal": (cleaned_query or original_query)[:700],
        "context": [],
        "constraints": [],
        "success_criteria": [],
        "unknowns": [],
        "user_preferences": [],
        "risk_level": "medium" if cleaned_query else "low",
        "complexity": complexity,
        "should_use_cmm": complexity != "simple",
        "parse_warnings": [warning],
        "source": "fallback",
    }


def fallback_conflict_report() -> dict:
    return {
        "agreements": [],
        "disagreements": [],
        "unresolved_tradeoffs": [],
        "premature_consensus_risks": [],
        "blind_spots": ["Conflict analysis failed."],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": 0.0,
        "parse_warnings": ["conflict_analysis_failed"],
        "source": "fallback",
    }


def fallback_meta_decision(reason: str, warning: str) -> dict:
    return {
        "decision": "SYNTHESIZE",
        "reason": reason,
        "missing_perspectives": [],
        "conflicts_to_resolve": [],
        "risks_to_address": [],
        "questions_to_answer": [],
        "next_actions": ["Proceed to planning."],
        "confidence": 0.0,
        "parse_warnings": [warning],
        "source": "state_machine_fallback",
    }


__all__ = [
    "empty_expert_bundle",
    "conservative_balance_report",
    "empty_deliberation_brief",
    "fallback_query_intake",
    "fallback_conflict_report",
    "fallback_meta_decision",
]
