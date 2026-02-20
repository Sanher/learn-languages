from __future__ import annotations

from datetime import date

from .scheduling import LanguageScheduleConfig, default_language_schedule_config


_DEFAULT_CONFIG = default_language_schedule_config()

def language_for_date(current_date: date, config: LanguageScheduleConfig | None = None) -> str:
    """Pick study language based on weekday policy.

    - Monday..Friday -> Japanese (ja)
    - Saturday/Sunday -> English (en)
    """
    active_config = config or _DEFAULT_CONFIG
    return active_config.language_for_weekday(current_date.weekday())
