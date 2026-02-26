from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from random import Random
from typing import Iterable, List

GAME_POOL = [
    "kanji_match",
    "kana_speed_round",
    "mora_romanization",
    "grammar_particle_fix",
    "sentence_order",
    "listening_gap_fill",
    "pronunciation_match",
    "context_quiz",
]


@dataclass
class LearnerSnapshot:
    learner_id: str
    streak_days: int = 0
    recent_accuracy: float = 0.0
    recent_games: List[str] | None = None


class DailyGamePlanner:
    """Plans 4-5 daily games while avoiding recent repeats."""

    def __init__(self, game_pool: Iterable[str] | None = None) -> None:
        self._pool = list(game_pool or GAME_POOL)

    def choose_games(self, learner: LearnerSnapshot, target_day: date) -> list[str]:
        rnd = Random(f"{learner.learner_id}:{target_day.isoformat()}")
        daily_count = 4 if rnd.random() < 0.5 else 5

        recent = learner.recent_games or []
        candidates = [g for g in self._pool if g not in recent]
        if len(candidates) < daily_count:
            candidates = self._pool.copy()

        candidates = self._apply_context_quiz_frequency_policy(candidates, learner, target_day)

        rnd.shuffle(candidates)
        return candidates[:daily_count]

    def _apply_context_quiz_frequency_policy(
        self,
        candidates: list[str],
        learner: LearnerSnapshot,
        target_day: date,
    ) -> list[str]:
        if "context_quiz" not in candidates:
            return candidates
        if self._is_context_quiz_day(learner, target_day):
            return candidates
        return [game for game in candidates if game != "context_quiz"]

    @staticmethod
    def _is_context_quiz_day(learner: LearnerSnapshot, target_day: date) -> bool:
        interval = DailyGamePlanner._context_quiz_interval_days(learner)
        anchor = sum(ord(char) for char in learner.learner_id) % interval
        return (target_day.toordinal() % interval) == anchor

    @staticmethod
    def _context_quiz_interval_days(learner: LearnerSnapshot) -> int:
        if learner.streak_days >= 30 or learner.recent_accuracy >= 0.9:
            return 7
        if learner.streak_days >= 14 or learner.recent_accuracy >= 0.82:
            return 5
        if learner.streak_days >= 7 or learner.recent_accuracy >= 0.72:
            return 3
        return 2

    @staticmethod
    def difficulty_for(learner: LearnerSnapshot) -> int:
        """Scales 1-10 using streak + recent accuracy."""
        base = 1 + min(5, learner.streak_days // 5)
        precision_boost = 2 if learner.recent_accuracy >= 0.85 else 1 if learner.recent_accuracy >= 0.7 else 0
        return min(10, base + precision_boost)
