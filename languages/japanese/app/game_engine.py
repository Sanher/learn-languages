from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from random import Random
from typing import Iterable, List

GAME_POOL = [
    "kanji_match",
    "kana_speed_round",
    "grammar_particle_fix",
    "sentence_order",
    "listening_gap_fill",
    "shadowing_score",
    "context_quiz",
]


@dataclass
class LearnerSnapshot:
    learner_id: str
    streak_days: int = 0
    recent_accuracy: float = 0.0
    recent_games: List[str] | None = None


class DailyGamePlanner:
    """Planifica 3-4 juegos diarios evitando repeticiones recientes."""

    def __init__(self, game_pool: Iterable[str] | None = None) -> None:
        self._pool = list(game_pool or GAME_POOL)

    def choose_games(self, learner: LearnerSnapshot, target_day: date) -> list[str]:
        rnd = Random(f"{learner.learner_id}:{target_day.isoformat()}")
        daily_count = 3 if rnd.random() < 0.5 else 4

        recent = learner.recent_games or []
        candidates = [g for g in self._pool if g not in recent]
        if len(candidates) < daily_count:
            candidates = self._pool.copy()

        rnd.shuffle(candidates)
        return candidates[:daily_count]

    @staticmethod
    def difficulty_for(learner: LearnerSnapshot) -> int:
        """Escala 1-10 usando streak + precisión reciente."""
        base = 1 + min(5, learner.streak_days // 5)
        precision_boost = 2 if learner.recent_accuracy >= 0.85 else 1 if learner.recent_accuracy >= 0.7 else 0
        return min(10, base + precision_boost)
