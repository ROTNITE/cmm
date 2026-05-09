"""Enhanced evaluation logger with detailed console output."""

import json
from datetime import datetime
from typing import Any


class EnhancedEvalLogger:
    """Logger for detailed evaluation debugging."""

    def __init__(self):
        self.enabled = True
        self.current_case = None
        self.indent_level = 0
        self.case_logs = []  # Store logs for current case
        self.log_file = None  # File to write logs to

    def set_log_file(self, file_path: str):
        """Set the file path for incremental log writing."""
        self.log_file = file_path

    def _print(self, message: str, level: int = 0):
        """Print with indentation and store in case_logs."""
        if not self.enabled:
            return
        indent = "  " * (self.indent_level + level)
        full_message = f"{indent}{message}"
        print(full_message)

        # Store in case logs
        if self.current_case:
            self.case_logs.append(full_message)

    def _separator(self, char: str = "=", length: int = 80):
        """Print separator line."""
        if self.enabled:
            sep_line = char * length
            print(sep_line)
            # Store in case logs
            if self.current_case:
                self.case_logs.append(sep_line)

    def case_start(self, case_id: str, query: str):
        """Log case start."""
        # Clear previous case logs and set current case first
        self.case_logs = []
        self.current_case = case_id

        self._separator()
        self._print(f"[*] CASE: {case_id}")
        self._print(f"Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        self._separator("-")
        self.indent_level = 0

    def flush_case_logs(self):
        """Write accumulated case logs to file."""
        if self.log_file and self.case_logs:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(self.case_logs))
                    f.write('\n\n')
            except Exception:
                pass  # Silently fail if can't write

    def stage_start(self, stage: str):
        """Log stage start."""
        self._print(f"\n[>] Stage: {stage.upper()}")
        self.indent_level = 1

    def stage_end(self, stage: str):
        """Log stage end."""
        self._print(f"[OK] {stage.upper()} complete")
        self.indent_level = 0

    def router_decision(self, mode: str, complexity: str, reasoning: str = ""):
        """Log router decision."""
        self._print(f"[R] Router: {mode} (complexity: {complexity})")
        if reasoning:
            self._print(f"    Reasoning: {reasoning[:200]}", level=0)

    def expert_contribution(self, role: str, perspective: str, valid: bool):
        """Log expert contribution."""
        status = "valid" if valid else "invalid"
        self._print(f"[E] Expert: {role} ({perspective}) - {status}")

    def plan_generated(self, plan: dict):
        """Log plan generation with full details."""
        self._print("[P] Plan generated:")

        if not isinstance(plan, dict):
            self._print("    ERROR: Plan is not a dict!", level=1)
            return

        # Main idea
        main_idea = plan.get("main_idea", "")
        if main_idea:
            self._print(f"    Main idea: {main_idea[:150]}", level=1)

        # Steps
        steps = plan.get("steps", [])
        if steps:
            self._print(f"    Steps ({len(steps)}):", level=1)
            for i, step in enumerate(steps[:5], 1):
                if isinstance(step, dict):
                    title = step.get("title", "")
                    self._print(f"      {i}. {title[:100]}", level=1)

        # Metadata
        source = plan.get("source", "unknown")
        raw_format = plan.get("raw_format", "unknown")
        self._print(f"    Source: {source}, Format: {raw_format}", level=1)

        # Warnings
        warnings = plan.get("parse_warnings", [])
        if warnings:
            self._print(f"    Warnings: {', '.join(warnings[:3])}", level=1)

    def plan_critique(self, status: str, critique: dict = None):
        """Log plan critique with detailed breakdown."""
        self._print(f"[P] Plan critique: {status}")

        if not critique or not isinstance(critique, dict):
            return

        # Overall score
        overall = critique.get("overall_score", 0.0)
        self._print(f"    Overall score: {overall:.2f}/10", level=1)

        # Scores breakdown
        scores = critique.get("scores", {})
        if scores:
            self._print("    Scores:", level=1)
            for key, value in list(scores.items())[:6]:
                self._print(f"      {key}: {value:.1f}", level=2)

        # Critical issues
        critical = critique.get("critical_blockers", []) or critique.get("critical_issues", [])
        if critical:
            self._print(f"    CRITICAL BLOCKERS ({len(critical)}):", level=1)
            for issue in critical[:3]:
                self._print(f"      - {str(issue)[:100]}", level=2)

        # Ignored items
        ignored_must = critique.get("ignored_must_address", [])
        ignored_risks = critique.get("ignored_risks", [])
        ignored_tradeoffs = critique.get("ignored_tradeoffs", [])

        if ignored_must:
            self._print(f"    Ignored must_address: {len(ignored_must)}", level=1)
        if ignored_risks:
            self._print(f"    Ignored risks: {len(ignored_risks)}", level=1)
        if ignored_tradeoffs:
            self._print(f"    Ignored tradeoffs: {len(ignored_tradeoffs)}", level=1)

        # Feedback
        feedback = critique.get("feedback", [])
        if feedback:
            self._print(f"    Feedback ({len(feedback)}):", level=1)
            for item in feedback[:3]:
                self._print(f"      - {str(item)[:100]}", level=2)

    def balance_analysis(self, balance: dict):
        """Log balance analysis results."""
        if not isinstance(balance, dict):
            return

        self._print("[B] Balance analysis:")

        # Missing perspectives
        missing = balance.get("missing_perspectives", [])
        if missing:
            self._print(f"    Missing perspectives: {', '.join(missing)}", level=1)

        # Blind spots
        blind_spots = balance.get("blind_spots", [])
        if blind_spots:
            self._print(f"    Blind spots ({len(blind_spots)}):", level=1)
            for spot in blind_spots[:3]:
                self._print(f"      - {str(spot)[:100]}", level=2)

        # Recommended action
        action = balance.get("recommended_action", "")
        if action:
            self._print(f"    Recommended action: {action}", level=1)

    def moderation_decision(self, decision: str, best_effort: bool):
        """Log moderation decision."""
        marker = " (best-effort)" if best_effort else ""
        self._print(f"[M] Moderation: {decision}{marker}")

    def judge_evaluation(self, winner: str, baseline_score: float, cmm_score: float, reason: str):
        """Log judge evaluation with detailed scores."""
        self._print(f"\n[J] Judge evaluation:")
        self._print(f"    Baseline overall: {baseline_score:.2f}/10", level=1)
        self._print(f"    CMM overall: {cmm_score:.2f}/10", level=1)
        self._print(f"    Delta: {cmm_score - baseline_score:+.2f}", level=1)
        self._print(f"    Winner: {winner}", level=1)
        if reason:
            self._print(f"    Reason: {reason[:200]}", level=1)

    def warning(self, message: str):
        """Log warning."""
        self._print(f"[!] Warning: {message}")

    def error(self, message: str):
        """Log error."""
        self._print(f"[X] Error: {message}")

    def case_end(self, case_id: str, winner: str, time_seconds: float = 0):
        """Log case end."""
        self._print(f"\n[+] Winner: {winner}")
        if time_seconds > 0:
            self._print(f"Time: {time_seconds:.2f}s")
        self._separator()
        self._print("")
        self.current_case = None
        self.indent_level = 0

    def info(self, message: str):
        """Log info message."""
        self._print(message)

    def summary(self):
        """Log summary (placeholder for compatibility)."""
        pass


# Global instance
_logger = None


def get_enhanced_logger() -> EnhancedEvalLogger:
    """Get or create the global enhanced logger."""
    global _logger
    if _logger is None:
        _logger = EnhancedEvalLogger()
    return _logger


def reset_enhanced_logger():
    """Reset the global logger."""
    global _logger
    _logger = EnhancedEvalLogger()
