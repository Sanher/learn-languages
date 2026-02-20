from __future__ import annotations

from .game_service import GameActivity, GameService


class GameServiceRegistry:
    """Coordinates game services and returns activities by language."""

    def __init__(self) -> None:
        self._services: dict[str, GameService] = {}

    def register(self, service: GameService) -> None:
        self._services[service.game_type] = service

    def list_game_types(self) -> list[str]:
        return sorted(self._services.keys())

    def get_daily_activities(
        self,
        language: str,
        games: list[str],
        level: int = 1,
    ) -> dict[str, GameActivity]:
        selected: dict[str, GameActivity] = {}

        for game in games:
            service = self._services.get(game)
            if service is None:
                continue

            activities = service.get_activities(language=language, level=level)
            if activities:
                selected[game] = activities[0]

        return selected
