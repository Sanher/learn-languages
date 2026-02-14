from __future__ import annotations

from datetime import date


def language_for_date(current_date: date) -> str:
    """Pick study language based on weekday policy.

    - Monday..Friday -> Japanese (ja)
    - Saturday/Sunday -> English (en)
    """

    return "ja" if current_date.weekday() < 5 else "en"
