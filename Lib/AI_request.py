"""Safe DeepSeek/OpenAI-compatible API client wrapper.

The module is intentionally safe to import without an API key and without
network access. A key is required only when ``send_to_AI`` is actually called.
"""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TOKEN_LIMIT = 850

_ENV_FILENAMES = (".env",)
_API_KEY_ENV_NAMES = ("OMNIROUTE_API_KEY", "CLAUDE_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "apy_key")


def _load_local_env_files() -> None:
    """Load local env files if available, without printing any values."""
    candidate_dirs = (Path.cwd(), Path(__file__).resolve().parent)
    seen: set[Path] = set()

    for directory in candidate_dirs:
        for filename in _ENV_FILENAMES:
            path = (directory / filename).resolve()
            if path in seen or not path.exists() or not path.is_file():
                continue
            seen.add(path)

            try:
                from dotenv import load_dotenv
            except Exception:
                _load_env_file_fallback(path)
            else:
                load_dotenv(path, override=False)


def _load_env_file_fallback(path: Path) -> None:
    """Small .env parser used only when python-dotenv is unavailable."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text().splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _get_api_key(explicit_api_key: str | None = None) -> str:
    """Return an API key from explicit input or supported env variables."""
    if explicit_api_key:
        return explicit_api_key

    _load_local_env_files()

    for name in _API_KEY_ENV_NAMES:
        value = os.getenv(name)
        if value:
            return value

    raise RuntimeError(
        "API key is not configured. Set OMNIROUTE_API_KEY, CLAUDE_API_KEY, or DEEPSEEK_API_KEY "
        "in the environment or in a local .env file before calling send_to_AI."
    )


def _get_base_url() -> str:
    """Return base URL from env or default."""
    _load_local_env_files()
    return (
        os.getenv("OMNIROUTE_BASE_URL")
        or os.getenv("CLAUDE_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )


def _count_words(value) -> int:
    try:
        text = str(value or "").strip()
    except Exception:
        return 0
    if not text:
        return 0
    return len(text.split())


def _auto_token_count(word_count: int) -> int:
    auto_k = 1.17
    auto_min = 500
    auto_max = 2000
    return int(min(auto_max, max(auto_min, int(auto_k * word_count)))) + 1


def _estimate_tokens(text: str) -> int:
    """Rough token estimation: ~0.75 tokens per word."""
    if not text:
        return 0
    words = len(str(text).split())
    return int(words * 0.75)


def _infer_purpose(system_prompt: str, user_prompt: str) -> str:
    """Infer the purpose of the AI call from the prompts."""
    combined = (system_prompt + " " + user_prompt).lower()

    if "router" in combined or "route query" in combined:
        return "router"
    elif "expert" in combined and "contribution" in combined:
        return "expert_agent"
    elif "plan" in combined and ("develop" in combined or "steps" in combined):
        return "planner"
    elif "critique" in combined or "plan critic" in combined:
        return "plan_critic"
    elif "meta" in combined and "moderator" in combined:
        return "meta_moderator"
    elif "moderate" in combined and "answer" in combined:
        return "answer_moderator"
    elif "conflict" in combined:
        return "conflict_analyzer"
    elif "balance" in combined:
        return "balance_analyzer"
    elif "deliberation" in combined:
        return "deliberation"
    elif "query intake" in combined or "cleaned_query" in combined:
        return "query_intake"
    elif "direct answer" in combined:
        return "direct_answer"
    elif "judge" in combined or "evaluation" in combined:
        return "judge"
    elif "baseline" in combined:
        return "baseline"
    return "unknown"


def send_to_AI(
    user_prompt: str,
    system_prompt: str = "",
    history: list | None = None,
    temp: float = 0.65,
    top_p: float = 0.9,
    tokens: int | None = None,
    model: str = DEFAULT_MODEL,
    stream: bool = False,
    api_key: str | None = None,
) -> str:
    """
    Send a request to a DeepSeek/OpenAI-compatible chat completions API.

    The function never prints or logs secret values. Missing dependencies,
    missing API keys, and API errors are returned as error strings to preserve
    the existing graceful-degradation behavior of the project.
    """
    try:
        resolved_api_key = _get_api_key(api_key)

        try:
            from openai import OpenAI
        except Exception as exc:
            return f"Error: openai package is not available: {exc}"

        client = OpenAI(api_key=resolved_api_key, base_url=_get_base_url())

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        if tokens is None:
            tokens = _auto_token_count(_count_words(messages))

        # Log before call
        logger = None
        purpose = ""
        estimated_prompt_tokens = 0
        try:
            from Lib.eval_logger import get_logger
            logger = get_logger()
            if logger and logger.enabled:
                purpose = _infer_purpose(system_prompt, user_prompt)
                prompt_text = f"{system_prompt}\n{user_prompt}"
                if history:
                    for msg in history:
                        if isinstance(msg, dict) and "content" in msg:
                            prompt_text += f"\n{msg['content']}"
                estimated_prompt_tokens = _estimate_tokens(prompt_text)
        except Exception:
            pass

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=tokens,
            temperature=temp,
            top_p=top_p,
            stream=stream,
        )

        result = response.choices[0].message.content

        # Log after call
        try:
            if logger and logger.enabled:
                estimated_completion_tokens = _estimate_tokens(result)
                total_tokens = estimated_prompt_tokens + estimated_completion_tokens
                logger.ai_call(
                    model=model,
                    prompt_tokens=estimated_prompt_tokens,
                    completion_tokens=estimated_completion_tokens,
                    total_tokens=total_tokens,
                    purpose=purpose,
                )
        except Exception:
            pass

        return result

    except Exception as exc:
        return f"Error: {exc}"
