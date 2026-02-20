from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GameActivity:
    activity_id: str
    language: str
    game_type: str
    prompt: str
    level: int = 1


class GameService(Protocol):
    game_type: str

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        """Returns game activities for a language."""


class InMemoryGameService:
    """Simple service to provide activities by language and level."""

    def __init__(self, game_type: str, activities_by_language: dict[str, list[GameActivity]]) -> None:
        self.game_type = game_type
        self._activities_by_language = activities_by_language

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        activities = self._activities_by_language.get(language, [])
        return [item for item in activities if item.level <= level]
