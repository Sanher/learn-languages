from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .scheduling import LanguageScheduleConfig, default_language_schedule_config
from .services import GameActivity, GameServiceRegistry


@dataclass(frozen=True)
class DailyGamesResult:
    language: str
    activities: dict[str, GameActivity]


class GamesOrchestrator:
    """Resolves active language and daily game activities by service."""

    def __init__(
        self,
        registry: GameServiceRegistry,
        schedule_config: LanguageScheduleConfig | None = None,
    ) -> None:
        self.registry = registry
        self.schedule_config = schedule_config or default_language_schedule_config()

    def daily_games(self, target: datetime, game_types: list[str], level: int = 1) -> DailyGamesResult:
        language = self.schedule_config.language_for_datetime(target)
        activities = self.registry.get_daily_activities(
            language=language,
            games=game_types,
            level=level,
        )
        return DailyGamesResult(language=language, activities=activities)
