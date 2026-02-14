from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class LearnerState:
    learner_id: str
    streak_days: int
    recent_accuracy: float
    recent_games_csv: str


class ProgressMemory:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learner_progress (
                    learner_id TEXT PRIMARY KEY,
                    streak_days INTEGER NOT NULL DEFAULT 0,
                    recent_accuracy REAL NOT NULL DEFAULT 0,
                    recent_games_csv TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def load_or_create(self, learner_id: str) -> LearnerState:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT learner_id, streak_days, recent_accuracy, recent_games_csv "
                "FROM learner_progress WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()

            if row:
                return LearnerState(*row)

            conn.execute(
                "INSERT INTO learner_progress (learner_id) VALUES (?)",
                (learner_id,),
            )
            return LearnerState(learner_id=learner_id, streak_days=0, recent_accuracy=0.0, recent_games_csv="")

    def save_session(self, learner_id: str, streak_days: int, recent_accuracy: float, recent_games: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_progress
                SET streak_days = ?,
                    recent_accuracy = ?,
                    recent_games_csv = ?
                WHERE learner_id = ?
                """,
                (streak_days, recent_accuracy, ",".join(recent_games[-4:]), learner_id),
            )
