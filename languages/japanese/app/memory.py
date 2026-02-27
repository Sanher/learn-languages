from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("learn_languages.japanese.memory")


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


@dataclass
class DailyTopicProgress:
    # Daily progression gate for topic lesson + 3 required games.
    learner_id: str
    day_iso: str
    language: str
    topic_key: str
    lesson_completed: int
    completed_daily_games_json: str

    def completed_daily_games(self) -> list[str]:
        raw = self.completed_daily_games_json.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed if str(item).strip()]


class ProgressMemory:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("memory_init db_path=%s", self.db_path)
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
            # Keep schema creation idempotent so add-on restarts are safe.
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_topic_progress (
                    learner_id TEXT NOT NULL,
                    day_iso TEXT NOT NULL,
                    language TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    lesson_completed INTEGER NOT NULL DEFAULT 0,
                    completed_daily_games_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (learner_id, day_iso, language, topic_key)
                )
                """
            )
        logger.info("memory_schema_ready db_path=%s", self.db_path)

    def load_or_create(self, learner_id: str) -> LearnerState:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT learner_id, streak_days, recent_accuracy, recent_games_csv "
                "FROM learner_progress WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()

            if row:
                logger.debug("learner_progress_loaded learner_id=%s", learner_id)
                return LearnerState(*row)

            conn.execute(
                "INSERT INTO learner_progress (learner_id) VALUES (?)",
                (learner_id,),
            )
            logger.info("learner_progress_created learner_id=%s", learner_id)
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
        logger.info(
            "session_saved learner_id=%s streak_days=%s recent_accuracy=%.3f recent_games_count=%s",
            learner_id,
            streak_days,
            recent_accuracy,
            len(recent_games),
        )

    def load_or_create_preferences(self, learner_id: str) -> LearnerPreferences:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT learner_id, preferred_language, levels_json "
                "FROM learner_preferences WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if row:
                logger.debug("learner_preferences_loaded learner_id=%s", learner_id)
                return LearnerPreferences(*row)

            default_levels = json.dumps({"ja": 1}, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO learner_preferences (learner_id, preferred_language, levels_json)
                VALUES (?, 'ja', ?)
                """,
                (learner_id, default_levels),
            )
            logger.info("learner_preferences_created learner_id=%s", learner_id)
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
        logger.info("preferred_language_updated learner_id=%s language=%s", learner_id, language)

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
        logger.info("language_level_updated learner_id=%s language=%s level=%s", learner_id, language, int(level))

    def level_for_language(self, learner_id: str, language: str, default_level: int = 1) -> int:
        prefs = self.load_or_create_preferences(learner_id)
        level = int(prefs.levels().get(language, default_level))
        logger.debug("language_level_loaded learner_id=%s language=%s level=%s", learner_id, language, level)
        return level

    def load_or_create_daily_topic_progress(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
    ) -> DailyTopicProgress:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT learner_id, day_iso, language, topic_key, lesson_completed, completed_daily_games_json
                FROM daily_topic_progress
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (learner_id, day_iso, language, topic_key),
            ).fetchone()
            if row:
                logger.debug(
                    "daily_topic_progress_loaded learner_id=%s day=%s language=%s topic=%s",
                    learner_id,
                    day_iso,
                    language,
                    topic_key,
                )
                return DailyTopicProgress(*row)

            conn.execute(
                """
                INSERT INTO daily_topic_progress (
                    learner_id, day_iso, language, topic_key, lesson_completed, completed_daily_games_json
                )
                VALUES (?, ?, ?, ?, 0, '[]')
                """,
                (learner_id, day_iso, language, topic_key),
            )
            logger.info(
                "daily_topic_progress_created learner_id=%s day=%s language=%s topic=%s",
                learner_id,
                day_iso,
                language,
                topic_key,
            )
            return DailyTopicProgress(
                learner_id=learner_id,
                day_iso=day_iso,
                language=language,
                topic_key=topic_key,
                lesson_completed=0,
                completed_daily_games_json="[]",
            )

    def mark_lesson_completed(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
    ) -> DailyTopicProgress:
        progress = self.load_or_create_daily_topic_progress(
            learner_id=learner_id,
            day_iso=day_iso,
            language=language,
            topic_key=topic_key,
        )
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE daily_topic_progress
                SET lesson_completed = 1
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (learner_id, day_iso, language, topic_key),
            )
        logger.info(
            "daily_lesson_completed learner_id=%s day=%s language=%s topic=%s",
            learner_id,
            day_iso,
            language,
            topic_key,
        )
        return DailyTopicProgress(
            learner_id=progress.learner_id,
            day_iso=progress.day_iso,
            language=progress.language,
            topic_key=progress.topic_key,
            lesson_completed=1,
            completed_daily_games_json=progress.completed_daily_games_json,
        )

    def mark_daily_game_completed(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
        game_type: str,
    ) -> DailyTopicProgress:
        progress = self.load_or_create_daily_topic_progress(
            learner_id=learner_id,
            day_iso=day_iso,
            language=language,
            topic_key=topic_key,
        )
        completed_games = progress.completed_daily_games()
        already_completed = game_type in completed_games
        if not already_completed:
            completed_games.append(game_type)

        completed_json = json.dumps(completed_games, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE daily_topic_progress
                SET completed_daily_games_json = ?
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (completed_json, learner_id, day_iso, language, topic_key),
            )
        logger.info(
            "daily_game_completed learner_id=%s day=%s language=%s topic=%s game_type=%s already_completed=%s completed_count=%s",
            learner_id,
            day_iso,
            language,
            topic_key,
            game_type,
            already_completed,
            len(completed_games),
        )
        return DailyTopicProgress(
            learner_id=progress.learner_id,
            day_iso=progress.day_iso,
            language=progress.language,
            topic_key=progress.topic_key,
            lesson_completed=progress.lesson_completed,
            completed_daily_games_json=completed_json,
        )
