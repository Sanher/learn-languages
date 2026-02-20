from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NotificationRule:
    weekday: int
    hour: int
    minute: int

    def matches(self, target: datetime) -> bool:
        return (
            target.weekday() == self.weekday
            and target.hour == self.hour
            and target.minute == self.minute
        )


@dataclass(frozen=True)
class LanguageScheduleConfig:
    default_language: str
    language_by_weekday: dict[int, str]
    notifications_by_language: dict[str, list[NotificationRule]]

    def language_for_weekday(self, weekday: int) -> str:
        return self.language_by_weekday.get(weekday, self.default_language)

    def language_for_datetime(self, target: datetime) -> str:
        return self.language_for_weekday(target.weekday())

    def pending_notifications(self, target: datetime) -> list[str]:
        notifications: list[str] = []
        for language, rules in self.notifications_by_language.items():
            if any(rule.matches(target) for rule in rules):
                notifications.append(language)
        return notifications


def default_language_schedule_config() -> LanguageScheduleConfig:
    return LanguageScheduleConfig(
        default_language="ja",
        language_by_weekday={
            0: "ja",
            1: "ja",
            2: "ja",
            3: "ja",
            4: "ja",
            5: "en",
            6: "en",
        },
        notifications_by_language={
            "ja": [
                NotificationRule(weekday=0, hour=8, minute=0),
                NotificationRule(weekday=2, hour=20, minute=30),
            ],
            "en": [
                NotificationRule(weekday=5, hour=10, minute=0),
                NotificationRule(weekday=6, hour=18, minute=0),
            ],
        },
    )
