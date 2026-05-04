"""expert_selector.py — Определение состава экспертной панели под запрос.

Роль модуля:
- Выдать список ролей, которые будут запускаться в экспертной экосистеме.
- По умолчанию использовать базовый набор ролей.
- При явном доменном запросе добавить +1 доменного эксперта.

Подход к надёжности:
- Домен определяется через короткий AI-вызов со строгим JSON-форматом.
- Любая ошибка/мусорный ответ => graceful fallback на базовые роли.
"""

from __future__ import annotations

import re

from Lib.AI_request import send_to_AI
from Lib.expert_roles import BASE_EXPERT_ROLES, ExpertRole
from Lib.json_utils import safe_json_loads


_ALLOWED_DOMAINS = {
    "medicine": "Medicine",
    "medical": "Medicine",
    "healthcare": "Medicine",
    "medicina": "Medicine",
    "медицина": "Medicine",
    "law": "Law",
    "legal": "Law",
    "юриспруденция": "Law",
    "право": "Law",
    "finance": "Finance",
    "financial": "Finance",
    "финансы": "Finance",
    "security": "Security",
    "cybersecurity": "Security",
    "безопасность": "Security",
    "education": "Education",
    "educational": "Education",
    "образование": "Education",
}


def _safe_json_loads(raw: str) -> dict | None:
    """Безопасно парсит JSON-объект из ответа модели.

    Сначала пробуем json.loads как есть, затем пытаемся извлечь
    первый JSON-объект из текста (если модель добавила лишние слова).
    """
    return safe_json_loads(raw)


def _normalize_domain(domain: str | None) -> str | None:
    """Приводит доменное имя к ограниченному словарю поддерживаемых доменов."""
    if not domain:
        return None

    key = str(domain).strip().lower()
    if not key:
        return None

    if key in _ALLOWED_DOMAINS:
        return _ALLOWED_DOMAINS[key]

    if key.endswith("s") and key[:-1] in _ALLOWED_DOMAINS:
        return _ALLOWED_DOMAINS[key[:-1]]

    return None


def _build_domain_expert(domain_name: str) -> ExpertRole:
    """Создаёт роль доменного эксперта для выбранного домена."""
    slug = re.sub(r"[^a-z0-9]+", "_", domain_name.lower()).strip("_") or "domain"
    return ExpertRole(
        key=f"domain_expert_{slug}",
        name=f"Domain Expert ({domain_name})",
        responsibility=(
            f"Проверка отраслевой корректности и практик в домене '{domain_name}'."
        ),
        system_prompt=(
            f"Ты доменный эксперт в области {domain_name}. "
            "Проверяй фактическую корректность, нормативные ограничения и профессиональные стандарты "
            "в рамках этого домена."
        ),
        perspective_tag="domain",
    )


def _detect_domain_need(query: str) -> tuple[bool, str | None]:
    """Определяет, нужен ли доменный эксперт для конкретного запроса."""
    system_prompt = (
        "Ты классификатор запроса. "
        "Верни строго JSON без markdown и без пояснений. "
        "Разрешенные домены: medicine, law, finance, security, education. "
        "Если домен не требуется, ставь need_domain_expert=false и domain=\"\". "
        "Формат: {\"need_domain_expert\": true/false, \"domain\": \"...\"}"
    )

    user_prompt = f"Определи необходимость доменного эксперта для запроса:\n{query}"

    raw = send_to_AI(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=0.25,
        tokens=180,
        model="deepseek-chat",
    )

    parsed = _safe_json_loads(raw if isinstance(raw, str) else "")
    if not parsed:
        return False, None

    need = parsed.get("need_domain_expert")
    domain = _normalize_domain(parsed.get("domain"))

    if isinstance(need, bool) and need and domain:
        return True, domain

    return False, None


def determine_expert_roles(query: str, max_roles: int = 5) -> list[ExpertRole]:
    """Возвращает итоговый набор экспертных ролей.

    Логика:
    - Берём базовые роли (до max_roles).
    - Если есть слот и AI подтвердил доменный характер запроса,
      добавляем одного domain_expert.
    - При любых ошибках возвращаем уже собранный безопасный минимум.
    """
    base_roles = list(BASE_EXPERT_ROLES)

    if max_roles <= 0:
        return []

    roles = base_roles[:max_roles]

    if len(roles) >= max_roles:
        return roles

    try:
        need_domain_expert, domain = _detect_domain_need(query)
    except Exception:
        return roles

    if need_domain_expert and domain and len(roles) < max_roles:
        roles.append(_build_domain_expert(domain))

    return roles
