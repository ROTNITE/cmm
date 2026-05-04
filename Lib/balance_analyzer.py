"""balance_analyzer.py — Первичный анализ баланса экспертных перспектив.

Назначение:
- Проверить, не доминирует ли одна перспектива.
- Выявить отсутствующие базовые перспективы.
- Дать короткие пояснения (notes), почему сделан такой вывод.

Ожидаемый вход:
- expert_bundle от expert_panel (или совместимый dict с contributions).
"""

from __future__ import annotations


_BASE_TAGS = ["strategy", "engineering", "risk", "user"]


def analyze_balance(expert_bundle: dict) -> dict:
    """Анализирует распределение перспектив в экспертных вкладах.

    Правила:
    - missing_perspectives: отсутствующие теги из базового набора.
    - если представленность базовых перспектив < 3, это фиксируется в notes.
    - если доля одного тега >= 60% от всех валидных вкладов,
      считаем, что найдено доминирование.
    """
    result = {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": [],
        "notes": [],
    }

    if not isinstance(expert_bundle, dict):
        result["missing_perspectives"] = list(_BASE_TAGS)
        result["notes"].append("expert_bundle is not a dict; fallback to missing all base perspectives.")
        return result

    contributions = expert_bundle.get("contributions", [])
    if not isinstance(contributions, list):
        contributions = []

    counts: dict[str, int] = {}
    total = 0

    for item in contributions:
        if not isinstance(item, dict):
            continue
        tag = item.get("perspective_tag")
        if not isinstance(tag, str):
            continue
        tag = tag.strip()
        if not tag:
            continue
        counts[tag] = counts.get(tag, 0) + 1
        total += 1

    present_base = [tag for tag in _BASE_TAGS if counts.get(tag, 0) > 0]
    missing_base = [tag for tag in _BASE_TAGS if counts.get(tag, 0) == 0]
    unique_count = len(present_base)

    if unique_count < 3:
        result["notes"].append(
            f"Only {unique_count} base perspective(s) represented; less than 3 indicates weak diversity."
        )

    result["missing_perspectives"] = missing_base
    if missing_base:
        result["notes"].append("Missing base perspectives: " + ", ".join(missing_base) + ".")
    else:
        result["notes"].append("All base perspectives are represented.")

    if total == 0:
        result["notes"].append("No valid contributions found for perspective analysis.")
        return result

    dominant_tag = None
    dominant_ratio = 0.0

    for tag, count in counts.items():
        ratio = count / total
        if ratio > dominant_ratio:
            dominant_ratio = ratio
            dominant_tag = tag

    if dominant_tag is not None and dominant_ratio >= 0.6:
        result["dominant_perspective_found"] = True
        result["dominant_perspective"] = dominant_tag
        result["notes"].append(
            f"Perspective '{dominant_tag}' dominates with {dominant_ratio:.0%} of contributions (>=60%)."
        )
    else:
        result["notes"].append("No dominant perspective detected (max share < 60%).")

    return result
