"""Central runtime configuration for CMM.

The tracked ``cmm_config.json`` keeps non-secret defaults such as model names,
provider base URL, and API-key environment variable names. Secrets should stay
in ``.env`` / environment variables, never in the tracked config.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "cmm_config.json"
LOCAL_CONFIG_PATH = REPO_ROOT / "cmm_config.local.json"
ENV_FILENAMES = (".env",)

DEFAULT_CONFIG: dict[str, Any] = {
    "profile": "gpt-4.1",
    "model": "",
    "judge_model": "",
    "api": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_env_names": [
            "OMNIROUTE_API_KEY",
            "CLAUDE_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "apy_key",
        ],
    },
    "defaults": {
        "max_iters": 2,
        "route_mode": "AUTO",
        "parallel_mode": "SEQUENTIAL",
        "max_workers": None,
        "max_deliberation_rounds": 1,
    },
    "profiles": {
        "gpt-4.1": {
            "model": "gpt-4.1",
            "judge_model": "gpt-4.1",
            "json_strategy": {
                "max_retries": 1,
                "retry_tokens_factor": 0.7,
                "repair_prompt": (
                    "Your previous output was invalid JSON. "
                    "Return one valid JSON object only. "
                    "No markdown. No prose."
                ),
            },
            "stage_settings": {
                "query_intake": {"tokens": 420, "temp": 0.15},
                "direct_answer": {"tokens": 700, "temp": 0.2},
                "expert_agent": {"tokens": 520, "temp": 0.15},
                "planner": {"tokens": 1000, "temp": 0.2},
                "plan_critic": {"tokens": 700, "temp": 0.15},
                "moderator": {"tokens": 900, "temp": 0.15},
                "conflict": {"tokens": 620, "temp": 0.15},
                "meta": {"tokens": 420, "temp": 0.15},
                "judge": {"tokens": 700, "temp": 0.1},
                "role_generator": {"tokens": 260, "temp": 0.1},
                "deliberation": {"tokens": 620, "temp": 0.2},
            },
            "direct_answer_style": {
                "concise_bias": True,
                "example_limit": 1,
                "max_chars": 900,
            },
            "judge_settings": {
                "max_retries": 1,
                "prefer_short_reason": True,
            },
        },
        "compat": {
            "model": "deepseek-chat",
            "judge_model": "deepseek-chat",
            "json_strategy": {
                "max_retries": 1,
                "retry_tokens_factor": 1.0,
                "repair_prompt": (
                    "Your previous output was invalid JSON. "
                    "Return only valid JSON matching the schema."
                ),
            },
            "stage_settings": {
                "query_intake": {"tokens": 650, "temp": 0.2},
                "direct_answer": {"tokens": 1200, "temp": 0.3},
                "expert_agent": {"tokens": 800, "temp": 0.2},
                "planner": {"tokens": 1500, "temp": 0.3},
                "plan_critic": {"tokens": 850, "temp": 0.2},
                "moderator": {"tokens": 1200, "temp": 0.25},
                "conflict": {"tokens": 800, "temp": 0.2},
                "meta": {"tokens": 550, "temp": 0.2},
                "judge": {"tokens": 900, "temp": 0.2},
                "role_generator": {"tokens": 350, "temp": 0.15},
                "deliberation": {"tokens": 750, "temp": 0.25},
            },
            "direct_answer_style": {
                "concise_bias": False,
                "example_limit": 2,
                "max_chars": 1400,
            },
            "judge_settings": {
                "max_retries": 1,
                "prefer_short_reason": False,
            },
        },
    },
}


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in _safe_dict(override).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_local_env_files() -> None:
    """Load local env files without printing any values."""
    candidate_dirs = (Path.cwd(), REPO_ROOT, Path(__file__).resolve().parent)
    seen: set[Path] = set()
    for directory in candidate_dirs:
        for filename in ENV_FILENAMES:
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


def _read_json_file(path: Path) -> dict:
    try:
        if not path.exists() or not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_config() -> dict:
    """Return merged config with cmm_config.json having HIGHEST priority for model/api settings.

    Priority order for model, judge_model, base_url (highest to lowest):
    1. cmm_config.json (tracked config file) - HIGHEST PRIORITY
    2. cmm_config.local.json (local overrides, not tracked)
    3. Environment variables
    4. DEFAULT_CONFIG (hardcoded defaults)

    Priority order for runtime settings (max_iters, route_mode, etc.):
    1. Environment variables - HIGHEST PRIORITY
    2. cmm_config.json
    3. cmm_config.local.json
    4. DEFAULT_CONFIG

    This ensures that model/api settings in cmm_config.json are always used,
    but runtime behavior can be overridden by environment variables.
    """
    config_path = Path(os.getenv("CMM_CONFIG_PATH") or DEFAULT_CONFIG_PATH).expanduser()
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()

    # Start with defaults
    config = deepcopy(DEFAULT_CONFIG)

    # Apply local config (low priority)
    config = _deep_merge(config, _read_json_file(LOCAL_CONFIG_PATH))

    # Apply tracked config (medium priority for runtime, high for model/api)
    tracked_config = _read_json_file(config_path)
    config = _deep_merge(config, tracked_config)

    # Apply profile defaults
    config = _apply_profile_defaults(config)

    # Apply env overrides for runtime settings (highest priority for runtime)
    config = _apply_env_overrides(config)

    # Force model/judge_model/base_url from tracked config (highest priority)
    if tracked_config:
        if "model" in tracked_config and str(tracked_config["model"]).strip():
            config["model"] = tracked_config["model"]
        if "judge_model" in tracked_config and str(tracked_config["judge_model"]).strip():
            config["judge_model"] = tracked_config["judge_model"]
        if "api" in tracked_config and isinstance(tracked_config["api"], dict):
            if "base_url" in tracked_config["api"] and str(tracked_config["api"]["base_url"]).strip():
                config.setdefault("api", {})["base_url"] = tracked_config["api"]["base_url"]

    return config


def _apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides for non-critical settings only.

    NOTE: model, judge_model, and base_url are NOT overridden by env vars.
    These must be set in cmm_config.json to ensure consistent behavior.
    Only runtime defaults like max_iters, route_mode, etc. can be overridden.
    """
    out = deepcopy(config)
    defaults = out.setdefault("defaults", {})

    # Allow env override for runtime behavior settings only
    for key, env_name in (
        ("route_mode", "CMM_ROUTE_MODE"),
        ("parallel_mode", "CMM_PARALLEL_MODE"),
    ):
        value = os.getenv(env_name)
        if value:
            defaults[key] = value

    for key, env_name in (
        ("max_iters", "CMM_MAX_ITERS"),
        ("max_workers", "CMM_MAX_WORKERS"),
        ("max_deliberation_rounds", "CMM_MAX_DELIBERATION_ROUNDS"),
    ):
        value = os.getenv(env_name)
        if value:
            try:
                defaults[key] = int(value)
            except ValueError:
                pass

    return out


def _apply_profile_defaults(config: dict) -> dict:
    out = deepcopy(config)
    profiles = _safe_dict(out.get("profiles"))
    profile_name = str(out.get("profile") or DEFAULT_CONFIG.get("profile") or "compat").strip()
    profile = _safe_dict(profiles.get(profile_name))
    if not profile:
        profile_name = "compat"
        profile = _safe_dict(profiles.get(profile_name))

    out["profile"] = profile_name

    if not str(out.get("model") or "").strip():
        out["model"] = profile.get("model") or DEFAULT_CONFIG["profiles"]["compat"]["model"]
    if not str(out.get("judge_model") or "").strip():
        out["judge_model"] = profile.get("judge_model") or out.get("model") or DEFAULT_CONFIG["profiles"]["compat"]["judge_model"]

    for key in ("json_strategy", "stage_settings", "direct_answer_style", "judge_settings"):
        out[key] = _deep_merge(_safe_dict(profile.get(key)), _safe_dict(out.get(key)))

    return out


def get_default_model(explicit: str | None = None) -> str:
    """Get the model to use.

    Priority (highest to lowest):
    1. explicit parameter (if provided) - HIGHEST for CLI/API calls
    2. cmm_config.json model field (if set)
    3. Profile default
    """
    if explicit and str(explicit).strip():
        return str(explicit)

    config = load_config()
    config_model = str(config.get("model") or "").strip()
    if config_model:
        return config_model

    return DEFAULT_CONFIG["profiles"]["compat"]["model"]


def get_judge_model(explicit: str | None = None, *, fallback_model: str | None = None) -> str:
    """Get the judge model to use.

    Priority (highest to lowest):
    1. explicit parameter (if provided) - HIGHEST for CLI/API calls
    2. fallback_model (when caller wants judge to follow main runtime model)
    3. cmm_config.json judge_model field (if set)
    4. Default model
    """
    if explicit and str(explicit).strip():
        return str(explicit)

    if fallback_model and str(fallback_model).strip():
        return str(fallback_model)

    config = load_config()
    config_judge = str(config.get("judge_model") or "").strip()
    if config_judge:
        return config_judge

    return get_default_model()


def get_model_profile_name(explicit: str | None = None) -> str:
    return str(explicit or load_config().get("profile") or DEFAULT_CONFIG.get("profile") or "compat")


def get_model_profile(explicit: str | None = None) -> dict:
    config = load_config()
    profile_name = get_model_profile_name(explicit)
    profiles = _safe_dict(config.get("profiles"))
    profile = _safe_dict(profiles.get(profile_name))
    if not profile:
        profile_name = "compat"
        profile = _safe_dict(profiles.get(profile_name))
    merged = {
        "name": profile_name,
        "model": config.get("model") or profile.get("model") or DEFAULT_CONFIG["profiles"]["compat"]["model"],
        "judge_model": config.get("judge_model") or profile.get("judge_model") or DEFAULT_CONFIG["profiles"]["compat"]["judge_model"],
        "json_strategy": _safe_dict(config.get("json_strategy")),
        "stage_settings": _safe_dict(config.get("stage_settings")),
        "direct_answer_style": _safe_dict(config.get("direct_answer_style")),
        "judge_settings": _safe_dict(config.get("judge_settings")),
    }
    return merged


def get_base_url() -> str:
    return str(_safe_dict(load_config().get("api")).get("base_url") or DEFAULT_CONFIG["api"]["base_url"])


def get_api_key_env_names() -> tuple[str, ...]:
    api = _safe_dict(load_config().get("api"))
    names: list[str] = []
    primary = api.get("api_key_env")
    if isinstance(primary, str) and primary.strip():
        names.append(primary.strip())
    for item in api.get("api_key_env_names") or []:
        if isinstance(item, str) and item.strip() and item.strip() not in names:
            names.append(item.strip())
    return tuple(names or DEFAULT_CONFIG["api"]["api_key_env_names"])


def get_default_options() -> dict:
    return deepcopy(_safe_dict(load_config().get("defaults")))


def get_json_strategy() -> dict:
    return deepcopy(_safe_dict(load_config().get("json_strategy")))


def get_stage_settings(stage: str, fallback: dict | None = None) -> dict:
    settings = _safe_dict(_safe_dict(load_config().get("stage_settings")).get(str(stage or "").strip()))
    return _deep_merge(_safe_dict(fallback), settings)


def get_direct_answer_style() -> dict:
    return deepcopy(_safe_dict(load_config().get("direct_answer_style")))


def get_judge_settings() -> dict:
    return deepcopy(_safe_dict(load_config().get("judge_settings")))


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_CONFIG_PATH",
    "LOCAL_CONFIG_PATH",
    "get_api_key_env_names",
    "get_base_url",
    "get_default_model",
    "get_default_options",
    "get_direct_answer_style",
    "get_json_strategy",
    "get_judge_model",
    "get_judge_settings",
    "get_model_profile",
    "get_model_profile_name",
    "get_stage_settings",
    "load_config",
    "load_local_env_files",
]
