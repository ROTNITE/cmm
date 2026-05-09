"""Interactive logging system for eval runs with token tracking."""

from __future__ import annotations

import sys
import time
from typing import Any


class EvalLogger:
    """Interactive logger for eval runs with agent and token tracking."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.total_tokens = 0
        self.total_cost = 0.0
        self.total_calls = 0
        self.agent_stack: list[str] = []
        self.case_start_time: float | None = None
        self.indent_level = 0
        self.log_file = None  # File to write logs to
        self.case_logs = []  # Store logs for current case

    def set_log_file(self, file_path: str):
        """Set the file path for incremental log writing."""
        self.log_file = file_path

    def _print(self, message: str, prefix: str = "", color: str = "") -> None:
        """Print with indentation and optional color."""
        if not self.enabled:
            return
        indent = "  " * self.indent_level
        colors = {
            "blue": "\033[94m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "red": "\033[91m",
            "cyan": "\033[96m",
            "magenta": "\033[95m",
            "reset": "\033[0m",
            "bold": "\033[1m",
        }
        color_code = colors.get(color, "")
        reset = colors["reset"] if color_code else ""
        full_message = f"{indent}{prefix}{message}"
        print(f"{color_code}{full_message}{reset}", flush=True)

        # Store in case logs (without color codes)
        self.case_logs.append(full_message)

    def case_start(self, case_id: str, query: str) -> None:
        """Log start of a case evaluation."""
        # Clear previous case logs
        self.case_logs = []

        self.case_start_time = time.time()
        self._print("=" * 80, color="bold")
        self._print(f"CASE: {case_id}", prefix="[*] ", color="bold")
        self._print(f"Query: {query[:100]}{'...' if len(query) > 100 else ''}", color="cyan")
        self._print("")

    def flush_case_logs(self):
        """Write accumulated case logs to file."""
        if self.log_file and self.case_logs:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(self.case_logs))
                    f.write('\n\n')
            except Exception:
                pass  # Silently fail if can't write

    def case_end(self, case_id: str, winner: str) -> None:
        """Log end of a case evaluation."""
        elapsed = time.time() - self.case_start_time if self.case_start_time else 0
        self._print("")
        self._print(f"Winner: {winner}", prefix="[+] ", color="green" if winner == "CMM" else "yellow")
        self._print(f"Time: {elapsed:.2f}s", color="cyan")
        self._print("=" * 80, color="bold")
        self._print("")

    def stage_start(self, stage: str) -> None:
        """Log start of a stage (baseline, cmm, judge)."""
        self._print(f"Stage: {stage.upper()}", prefix="[>] ", color="blue")
        self.indent_level += 1

    def stage_end(self, stage: str) -> None:
        """Log end of a stage."""
        self.indent_level -= 1
        self._print(f"[OK] {stage.upper()} complete", color="green")
        self._print("")

    def agent_start(self, agent_name: str, context: str = "") -> None:
        """Log start of an agent."""
        self.agent_stack.append(agent_name)
        context_str = f" ({context})" if context else ""
        self._print(f"Agent: {agent_name}{context_str}", prefix="[A] ", color="magenta")
        self.indent_level += 1

    def agent_end(self, agent_name: str, status: str = "success") -> None:
        """Log end of an agent."""
        if self.agent_stack and self.agent_stack[-1] == agent_name:
            self.agent_stack.pop()
        self.indent_level -= 1
        status_icon = "[OK]" if status == "success" else "[!!]"
        status_color = "green" if status == "success" else "red"
        self._print(f"{status_icon} {agent_name} {status}", color=status_color)

    def ai_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        purpose: str = "",
    ) -> None:
        """Log an AI API call with token usage."""
        self.total_tokens += total_tokens
        self.total_calls += 1

        # Calculate cost (Claude Sonnet 4: $3/M input, $15/M output)
        input_cost = (prompt_tokens / 1_000_000) * 3.0
        output_cost = (completion_tokens / 1_000_000) * 15.0
        call_cost = input_cost + output_cost
        self.total_cost += call_cost

        purpose_str = f" [{purpose}]" if purpose else ""
        self._print(
            f"AI Call #{self.total_calls}{purpose_str}",
            prefix="[AI] ",
            color="yellow",
        )
        self.indent_level += 1
        self._print(f"Model: {model}", color="cyan")
        self._print(
            f"Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total",
            color="cyan",
        )
        self._print(f"Cost: ${input_cost:.6f} input + ${output_cost:.6f} output = ${call_cost:.6f} total", color="cyan")
        self._print(f"Running total: {self.total_tokens} tokens, ${self.total_cost:.4f} cost", color="cyan")
        self.indent_level -= 1

    def router_decision(self, mode: str, complexity: str, reasoning: str = "") -> None:
        """Log router decision."""
        self._print(f"Router: {mode} (complexity: {complexity})", prefix="[R] ", color="blue")
        if reasoning:
            self.indent_level += 1
            self._print(f"Reasoning: {reasoning[:150]}{'...' if len(reasoning) > 150 else ''}", color="cyan")
            self.indent_level -= 1

    def expert_contribution(self, role: str, perspective: str, valid: bool) -> None:
        """Log expert agent contribution."""
        status = "valid" if valid else "invalid JSON"
        status_color = "green" if valid else "red"
        self._print(
            f"Expert: {role} ({perspective}) - {status}",
            prefix="[E] ",
            color=status_color,
        )

    def plan_critique(self, status: str, feedback: str = "") -> None:
        """Log plan critique result."""
        self._print(f"Plan critique: {status}", prefix="[P] ", color="yellow")
        if feedback:
            self.indent_level += 1
            self._print(f"Feedback: {feedback[:150]}{'...' if len(feedback) > 150 else ''}", color="cyan")
            self.indent_level -= 1

    def moderation_decision(self, decision: str, best_effort: bool) -> None:
        """Log moderation decision."""
        effort = " (best-effort)" if best_effort else ""
        self._print(f"Moderation: {decision}{effort}", prefix="[M] ", color="yellow")

    def warning(self, message: str) -> None:
        """Log a warning."""
        self._print(f"Warning: {message}", prefix="[!] ", color="yellow")

    def error(self, message: str) -> None:
        """Log an error."""
        self._print(f"Error: {message}", prefix="[X] ", color="red")

    def info(self, message: str) -> None:
        """Log general info."""
        self._print(message, color="cyan")

    def summary(self) -> None:
        """Print final summary."""
        self._print("")
        self._print("=" * 80, color="bold")
        self._print("EVALUATION SUMMARY", prefix="[#] ", color="bold")
        self._print(f"Total AI calls: {self.total_calls}", color="cyan")
        self._print(f"Total tokens used: {self.total_tokens:,}", color="cyan")

        # Estimate cost (example rates, adjust as needed)
        # DeepSeek: ~$0.14 per 1M input tokens, ~$0.28 per 1M output tokens
        # Rough estimate assuming 50/50 split
        estimated_cost = (self.total_tokens / 1_000_000) * 0.21
        self._print(f"Estimated cost: ${estimated_cost:.4f}", color="green")
        self._print("=" * 80, color="bold")


# Global logger instance
_global_logger: EvalLogger | None = None


def get_logger() -> EvalLogger:
    """Get or create the global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = EvalLogger(enabled=False)
    return _global_logger


def set_logger_enabled(enabled: bool) -> None:
    """Enable or disable logging."""
    logger = get_logger()
    logger.enabled = enabled


def reset_logger() -> None:
    """Reset the global logger."""
    global _global_logger
    _global_logger = EvalLogger(enabled=False)
