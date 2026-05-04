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
_API_KEY_ENV_NAMES = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "apy_key")


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
        "API key is not configured. Set DEEPSEEK_API_KEY in the environment "
        "or in a local .env file before calling send_to_AI."
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
    auto_min = 50
    auto_max = 1000
    return int(min(auto_max, max(auto_min, int(auto_k * word_count)))) + 1


def send_to_AI(
    user_prompt: str,
    system_prompt: str = "",
    history: list | None = None,
    temp: float = 0.65,
    top_p: float = 0.9,
    tokens: int = DEFAULT_TOKEN_LIMIT,
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

        client = OpenAI(api_key=resolved_api_key, base_url=DEFAULT_BASE_URL)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        if tokens == DEFAULT_TOKEN_LIMIT:
            tokens = _auto_token_count(_count_words(messages))

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=tokens,
            temperature=temp,
            top_p=top_p,
            stream=stream,
        )

        return response.choices[0].message.content

    except Exception as exc:
        return f"Error: {exc}"
