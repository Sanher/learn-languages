from __future__ import annotations

import json
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


@dataclass
class LearnerPreferences:
    learner_id: str
    preferred_language: str
    levels_json: str

    def levels(self) -> dict[str, int]:
        raw = self.levels_json.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return {str(key): int(value) for key, value in parsed.items()}


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learner_preferences (
                    learner_id TEXT PRIMARY KEY,
                    preferred_language TEXT NOT NULL DEFAULT 'ja',
                    levels_json TEXT NOT NULL DEFAULT '{"ja": 1}'
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

    def load_or_create_preferences(self, learner_id: str) -> LearnerPreferences:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT learner_id, preferred_language, levels_json "
                "FROM learner_preferences WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if row:
                return LearnerPreferences(*row)

            default_levels = json.dumps({"ja": 1}, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO learner_preferences (learner_id, preferred_language, levels_json)
                VALUES (?, 'ja', ?)
                """,
                (learner_id, default_levels),
            )
            return LearnerPreferences(
                learner_id=learner_id,
                preferred_language="ja",
                levels_json=default_levels,
            )

    def set_preferred_language(self, learner_id: str, language: str) -> None:
        prefs = self.load_or_create_preferences(learner_id)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_preferences
                SET preferred_language = ?
                WHERE learner_id = ?
                """,
                (language, learner_id),
            )
        # Ensure row exists and keep levels json valid.
        _ = prefs

    def set_language_level(self, learner_id: str, language: str, level: int) -> None:
        prefs = self.load_or_create_preferences(learner_id)
        levels = prefs.levels()
        levels[language] = int(level)

        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_preferences
                SET levels_json = ?
                WHERE learner_id = ?
                """,
                (json.dumps(levels, ensure_ascii=False), learner_id),
            )

    def level_for_language(self, learner_id: str, language: str, default_level: int = 1) -> int:
        prefs = self.load_or_create_preferences(learner_id)
        return int(prefs.levels().get(language, default_level))
