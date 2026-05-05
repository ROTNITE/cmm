"""Legacy query formalization compatibility helper.

The active CMM intake path is ``Lib.query_intake``. This module is kept for old
manual scripts that call ``formalization(...)`` directly; it must remain silent
by default and must not be treated as the main state-machine intake layer.
"""


import re

from Lib.AI_request import send_to_AI


def formalization(inp_text: str) -> str:
    """
    :param inp_text: запрос юзера
    :return: формализированный запрос юзера
    """

    def _code_formalization(inp: str) -> str:
        """
        Убирает лишние слова-повторы, нормализует кавычки, тире и т.п.
        Только механическая обработка без изменения смысла.
        """

        if not inp:
            return ""

        text = str(inp)

        # --- 1. Нормализация кавычек ---
        quote_map = {
            "«": '"', "»": '"',
            "“": '"', "”": '"',
            "„": '"', "‟": '"',
            "’": "'", "‘": "'",
            "`": "'",
        }
        for k, v in quote_map.items():
            text = text.replace(k, v)

        # --- 2. Нормализация тире ---
        # разные unicode тире → обычный дефис
        text = re.sub(r"[–—−]", "-", text)

        # --- 3. Удаляем растянутые буквы (оооо → оо) ---
        # оставляем максимум 2 одинаковых символа подряд
        text = re.sub(r"(.)\1{2,}", r"\1\1", text)

        # --- 4. Убираем повторы пунктуации ---
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)
        text = re.sub(r"[.]{3,}", "...", text)
        text = re.sub(r"[,]{2,}", ",", text)

        # --- 5. Нормализация пробелов ---
        text = re.sub(r"\s+", " ", text)  # много пробелов → один
        text = re.sub(r"\s+([,.!?])", r"\1", text)  # пробел перед знаками убрать

        # --- 6. Удаляем повторяющиеся слова подряд ---
        # пример: "привет привет привет" -> "привет привет"
        def _dedupe_words(match):
            w = match.group(1)
            return f"{w} {w}"

        text = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", _dedupe_words, text, flags=re.IGNORECASE)

        # --- 7. Чуть подравняем дефисы ---
        # " - " оставляем, но множественные дефисы схлопываем
        text = re.sub(r"-{2,}", "-", text)

        # --- 8. Финальный trim ---
        text = text.strip()

        return text

    def _AI_formalization(inp: str) -> str:
        """
        Лёгкая формализация текста с помощью ИИ.
        Задача — немного улучшить формулировку,
        НЕ меняя смысл и НЕ добавляя новую информацию.
        """

        system_prompt = (
            "Ты агент формализации пользовательских запросов.\n"
            "Твоя задача — слегка улучшить читаемость текста.\n"
            "Строгие правила:\n"
            "1) НЕ меняй смысл.\n"
            "2) НЕ добавляй новую информацию.\n"
            "3) НЕ убирай важные детали.\n"
            "4) Исправляй только стиль, порядок слов и явные языковые огрехи.\n"
            "5) Верни ТОЛЬКО итоговый текст без комментариев."
        )

        user_prompt = (
            "Слегка формализуй следующий запрос пользователя, "
            "сохранив исходный смысл:\n\n"
            f"{inp}"
        )

        resp = send_to_AI(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temp=0.2,  # низкая температура = меньше фантазии
            tokens=120,  # 15 слишком мало — ответ часто обрезается
            model="deepseek-chat"
        )

        # защита от None / ошибок
        if not resp or isinstance(resp, Exception):
            return inp

        return resp.strip()

    # --- Основной пайплайн ---
    if not inp_text:
        return ""

    code_cleaned = _code_formalization(inp_text)

    ai_cleaned = _AI_formalization(code_cleaned)

    if not ai_cleaned:
        return code_cleaned

    return ai_cleaned
