from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

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
    secondary_translation_lang: str

    def levels(self) -> dict[str, int]:
        raw = self.levels_json.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return {str(key): int(value) for key, value in parsed.items()}

    def secondary_translation_language(self) -> str | None:
        value = (self.secondary_translation_lang or "").strip().lower()
        return value or None


@dataclass
class DailyTopicProgress:
    # Daily progression gate for topic lesson + rotating required games.
    learner_id: str
    day_iso: str
    language: str
    topic_key: str
    lesson_completed: int
    completed_daily_games_json: str
    level_state: int
    daily_score: int
    daily_game_scores_json: str
    daily_game_failures_json: str

    def completed_daily_games(self) -> list[str]:
        raw = self.completed_daily_games_json.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed if str(item).strip()]

    def daily_game_scores(self) -> dict[str, int]:
        raw = self.daily_game_scores_json.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        scores: dict[str, int] = {}
        for game_type, value in parsed.items():
            try:
                scores[str(game_type)] = int(value)
            except (TypeError, ValueError):
                continue
        return scores

    def daily_game_failures(self) -> dict[str, int]:
        raw = self.daily_game_failures_json.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        failures: dict[str, int] = {}
        for game_type, value in parsed.items():
            try:
                failures[str(game_type)] = int(value)
            except (TypeError, ValueError):
                continue
        return failures


@dataclass
class LearnerAssessmentState:
    learner_id: str
    weekly_exam_last_day_iso: str
    weekly_exam_passed_count: int
    level_exams_passed_json: str

    def level_exams_passed(self) -> dict[str, int]:
        raw = self.level_exams_passed_json.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        result: dict[str, int] = {}
        for key, value in parsed.items():
            try:
                result[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return result


@dataclass
class ClosedTopic:
    learner_id: str
    language: str
    topic_key: str
    closed_day_iso: str
    closed_level: int
    reason: str


@dataclass
class ItemReviewState:
    learner_id: str
    language: str
    topic_key: str
    game_type: str
    item_id: str
    due_day_iso: str
    interval_days: int
    ease: float
    repetitions: int
    lapses: int
    last_score: int
    last_seen_day_iso: str


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
                    levels_json TEXT NOT NULL DEFAULT '{"ja": 1}',
                    secondary_translation_lang TEXT NOT NULL DEFAULT ''
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
                    level_state INTEGER NOT NULL DEFAULT 1,
                    daily_score INTEGER NOT NULL DEFAULT 0,
                    daily_game_scores_json TEXT NOT NULL DEFAULT '{}',
                    daily_game_failures_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (learner_id, day_iso, language, topic_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learner_assessment_state (
                    learner_id TEXT PRIMARY KEY,
                    weekly_exam_last_day_iso TEXT NOT NULL DEFAULT '',
                    weekly_exam_passed_count INTEGER NOT NULL DEFAULT 0,
                    level_exams_passed_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS closed_topics (
                    learner_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    closed_day_iso TEXT NOT NULL,
                    closed_level INTEGER NOT NULL DEFAULT 1,
                    reason TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (learner_id, language, topic_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS item_review_state (
                    learner_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    game_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    due_day_iso TEXT NOT NULL,
                    interval_days INTEGER NOT NULL DEFAULT 1,
                    ease REAL NOT NULL DEFAULT 2.5,
                    repetitions INTEGER NOT NULL DEFAULT 0,
                    lapses INTEGER NOT NULL DEFAULT 0,
                    last_score INTEGER NOT NULL DEFAULT 0,
                    last_seen_day_iso TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (learner_id, language, topic_key, game_type, item_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_cache (
                    cache_key TEXT PRIMARY KEY,
                    source_text TEXT NOT NULL,
                    source_language TEXT NOT NULL DEFAULT 'en',
                    target_language TEXT NOT NULL,
                    context TEXT NOT NULL DEFAULT '',
                    translated_text TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_lessons_cache (
                    language TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    lessons_by_level_json TEXT NOT NULL DEFAULT '{}',
                    updated_at_iso TEXT NOT NULL DEFAULT '',
                    refresh_required INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (language, topic_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topic_sequence_cache (
                    language TEXT PRIMARY KEY,
                    topics_json TEXT NOT NULL DEFAULT '[]',
                    updated_at_iso TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'fallback'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_item_review_due
                ON item_review_state (learner_id, language, due_day_iso)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_item_review_topic_due
                ON item_review_state (learner_id, language, topic_key, due_day_iso)
                """
            )
            # Backward-compatible migrations for existing addon databases.
            self._ensure_column(conn, "daily_topic_progress", "level_state", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "daily_topic_progress", "daily_score", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "daily_topic_progress", "daily_game_scores_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "daily_topic_progress", "daily_game_failures_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "learner_preferences", "secondary_translation_lang", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topic_lessons_cache", "refresh_required", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "topic_sequence_cache", "source", "TEXT NOT NULL DEFAULT 'fallback'")
        logger.info("memory_schema_ready db_path=%s", self.db_path)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_ddl: str) -> None:
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column in columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_ddl}")
        logger.info("memory_schema_column_added table=%s column=%s", table, column)

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
                "SELECT learner_id, preferred_language, levels_json, COALESCE(secondary_translation_lang, '') "
                "FROM learner_preferences WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if row:
                logger.debug("learner_preferences_loaded learner_id=%s", learner_id)
                return LearnerPreferences(*row)

            default_levels = json.dumps({"ja": 1}, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO learner_preferences (learner_id, preferred_language, levels_json, secondary_translation_lang)
                VALUES (?, 'ja', ?, '')
                """,
                (learner_id, default_levels),
            )
            logger.info("learner_preferences_created learner_id=%s", learner_id)
            return LearnerPreferences(
                learner_id=learner_id,
                preferred_language="ja",
                levels_json=default_levels,
                secondary_translation_lang="",
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

    def set_secondary_translation_language(self, learner_id: str, secondary_language: str | None) -> None:
        normalized = (secondary_language or "").strip().lower()
        _ = self.load_or_create_preferences(learner_id)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_preferences
                SET secondary_translation_lang = ?
                WHERE learner_id = ?
                """,
                (normalized, learner_id),
            )
        logger.info("secondary_translation_language_updated learner_id=%s secondary_language=%s", learner_id, normalized or "off")

    def load_cached_translation(self, cache_key: str) -> str | None:
        normalized_key = str(cache_key or "").strip()
        if not normalized_key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT translated_text
                FROM translation_cache
                WHERE cache_key = ?
                """,
                (normalized_key,),
            ).fetchone()
        if not row:
            return None
        translated = str(row[0] or "").strip()
        return translated or None

    def save_cached_translation(
        self,
        *,
        cache_key: str,
        source_text: str,
        source_language: str,
        target_language: str,
        context: str,
        translated_text: str,
        updated_at_iso: str,
    ) -> None:
        normalized_key = str(cache_key or "").strip()
        if not normalized_key:
            return
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO translation_cache (
                    cache_key, source_text, source_language, target_language, context, translated_text, updated_at_iso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cache_key) DO UPDATE SET
                    source_text = excluded.source_text,
                    source_language = excluded.source_language,
                    target_language = excluded.target_language,
                    context = excluded.context,
                    translated_text = excluded.translated_text,
                    updated_at_iso = excluded.updated_at_iso
                """,
                (
                    normalized_key,
                    str(source_text or ""),
                    str(source_language or "en"),
                    str(target_language or ""),
                    str(context or ""),
                    str(translated_text or ""),
                    str(updated_at_iso or ""),
                ),
            )

    def load_topic_lessons_cache(self, *, language: str, topic_key: str) -> tuple[dict[int, dict[str, Any]] | None, bool]:
        normalized_language = str(language or "").strip().lower()
        normalized_topic = str(topic_key or "").strip()
        if not normalized_language or not normalized_topic:
            return None, False
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT lessons_by_level_json, COALESCE(refresh_required, 0)
                FROM topic_lessons_cache
                WHERE language = ? AND topic_key = ?
                """,
                (normalized_language, normalized_topic),
            ).fetchone()
        if row is None:
            return None, False

        raw_json = str(row[0] or "").strip()
        refresh_required = int(row[1] or 0) > 0
        if not raw_json:
            return None, refresh_required

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("topic_lessons_cache_invalid_json language=%s topic=%s", normalized_language, normalized_topic)
            return None, refresh_required
        if not isinstance(parsed, dict):
            return None, refresh_required

        lessons_by_level: dict[int, dict[str, Any]] = {}
        for raw_level, raw_payload in parsed.items():
            try:
                level = int(raw_level)
            except (TypeError, ValueError):
                continue
            if not isinstance(raw_payload, dict):
                continue
            lessons_by_level[level] = dict(raw_payload)
        if not lessons_by_level:
            return None, refresh_required
        return lessons_by_level, refresh_required

    def save_topic_lessons_cache(
        self,
        *,
        language: str,
        topic_key: str,
        lessons_by_level: dict[int, dict[str, Any]],
        updated_at_iso: str,
        refresh_required: bool = False,
    ) -> None:
        normalized_language = str(language or "").strip().lower()
        normalized_topic = str(topic_key or "").strip()
        if not normalized_language or not normalized_topic:
            return

        normalized_payload: dict[str, dict[str, Any]] = {}
        for level, payload in lessons_by_level.items():
            try:
                key = str(int(level))
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                normalized_payload[key] = dict(payload)
        if not normalized_payload:
            return

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO topic_lessons_cache (
                    language, topic_key, lessons_by_level_json, updated_at_iso, refresh_required
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (language, topic_key) DO UPDATE SET
                    lessons_by_level_json = excluded.lessons_by_level_json,
                    updated_at_iso = excluded.updated_at_iso,
                    refresh_required = excluded.refresh_required
                """,
                (
                    normalized_language,
                    normalized_topic,
                    json.dumps(normalized_payload, ensure_ascii=False),
                    str(updated_at_iso or ""),
                    1 if bool(refresh_required) else 0,
                ),
            )
        logger.info(
            "topic_lessons_cache_saved language=%s topic=%s levels=%s refresh_required=%s",
            normalized_language,
            normalized_topic,
            len(normalized_payload),
            bool(refresh_required),
        )

    def set_topic_lessons_refresh_required(self, *, language: str, topic_key: str, required: bool = True) -> None:
        normalized_language = str(language or "").strip().lower()
        normalized_topic = str(topic_key or "").strip()
        if not normalized_language or not normalized_topic:
            return
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO topic_lessons_cache (
                    language, topic_key, lessons_by_level_json, updated_at_iso, refresh_required
                )
                VALUES (?, ?, '{}', '', ?)
                ON CONFLICT (language, topic_key) DO UPDATE SET
                    refresh_required = excluded.refresh_required
                """,
                (
                    normalized_language,
                    normalized_topic,
                    1 if bool(required) else 0,
                ),
            )
        logger.info(
            "topic_lessons_refresh_flag_updated language=%s topic=%s required=%s",
            normalized_language,
            normalized_topic,
            bool(required),
        )

    def load_topic_sequence_cache(self, *, language: str) -> tuple[list[dict[str, Any]] | None, str]:
        normalized_language = str(language or "").strip().lower()
        if not normalized_language:
            return None, "fallback"
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT topics_json, COALESCE(source, 'fallback')
                FROM topic_sequence_cache
                WHERE language = ?
                """,
                (normalized_language,),
            ).fetchone()
        if row is None:
            return None, "fallback"
        raw_json = str(row[0] or "").strip()
        source = str(row[1] or "fallback").strip().lower() or "fallback"
        if not raw_json:
            return None, source
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("topic_sequence_cache_invalid_json language=%s", normalized_language)
            return None, source
        if not isinstance(parsed, list):
            return None, source
        topics: list[dict[str, Any]] = []
        for raw_item in parsed:
            if isinstance(raw_item, dict):
                topics.append(dict(raw_item))
        if not topics:
            return None, source
        return topics, source

    def save_topic_sequence_cache(
        self,
        *,
        language: str,
        topics: list[dict[str, Any]],
        updated_at_iso: str,
        source: str = "fallback",
    ) -> None:
        normalized_language = str(language or "").strip().lower()
        if not normalized_language:
            return

        normalized_topics: list[dict[str, Any]] = []
        for row in topics:
            if isinstance(row, dict):
                normalized_topics.append(dict(row))
        if not normalized_topics:
            return
        normalized_source = str(source or "fallback").strip().lower() or "fallback"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO topic_sequence_cache (language, topics_json, updated_at_iso, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (language) DO UPDATE SET
                    topics_json = excluded.topics_json,
                    updated_at_iso = excluded.updated_at_iso,
                    source = excluded.source
                """,
                (
                    normalized_language,
                    json.dumps(normalized_topics, ensure_ascii=False),
                    str(updated_at_iso or ""),
                    normalized_source,
                ),
            )
        logger.info(
            "topic_sequence_cache_saved language=%s topics=%s source=%s",
            normalized_language,
            len(normalized_topics),
            normalized_source,
        )

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
                SELECT learner_id, day_iso, language, topic_key, lesson_completed, completed_daily_games_json,
                       level_state, daily_score, daily_game_scores_json, daily_game_failures_json
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
                    learner_id, day_iso, language, topic_key, lesson_completed, completed_daily_games_json,
                    level_state, daily_score, daily_game_scores_json, daily_game_failures_json
                )
                VALUES (?, ?, ?, ?, 0, '[]', 1, 0, '{}', '{}')
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
                level_state=1,
                daily_score=0,
                daily_game_scores_json="{}",
                daily_game_failures_json="{}",
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
            level_state=progress.level_state,
            daily_score=progress.daily_score,
            daily_game_scores_json=progress.daily_game_scores_json,
            daily_game_failures_json=progress.daily_game_failures_json,
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
            level_state=progress.level_state,
            daily_score=progress.daily_score,
            daily_game_scores_json=progress.daily_game_scores_json,
            daily_game_failures_json=progress.daily_game_failures_json,
        )

    def set_daily_level_state(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
        level_state: int,
    ) -> DailyTopicProgress:
        progress = self.load_or_create_daily_topic_progress(
            learner_id=learner_id,
            day_iso=day_iso,
            language=language,
            topic_key=topic_key,
        )
        normalized = int(max(1, level_state))
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE daily_topic_progress
                SET level_state = ?
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (normalized, learner_id, day_iso, language, topic_key),
            )
        logger.info(
            "daily_level_state_saved learner_id=%s day=%s language=%s topic=%s level_state=%s",
            learner_id,
            day_iso,
            language,
            topic_key,
            normalized,
        )
        return DailyTopicProgress(
            learner_id=progress.learner_id,
            day_iso=progress.day_iso,
            language=progress.language,
            topic_key=progress.topic_key,
            lesson_completed=progress.lesson_completed,
            completed_daily_games_json=progress.completed_daily_games_json,
            level_state=normalized,
            daily_score=progress.daily_score,
            daily_game_scores_json=progress.daily_game_scores_json,
            daily_game_failures_json=progress.daily_game_failures_json,
        )

    def upsert_daily_game_score(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
        game_type: str,
        score: int,
        allowed_daily_games: list[str],
        max_total_score: int = 400,
    ) -> DailyTopicProgress:
        progress = self.load_or_create_daily_topic_progress(
            learner_id=learner_id,
            day_iso=day_iso,
            language=language,
            topic_key=topic_key,
        )
        normalized_score = max(0, min(100, int(score)))
        scores = progress.daily_game_scores()
        filtered_scores = {game: int(scores.get(game, 0)) for game in allowed_daily_games}
        filtered_scores[game_type] = normalized_score
        total = min(max_total_score, sum(max(0, min(100, int(value))) for value in filtered_scores.values()))
        scores_json = json.dumps(filtered_scores, ensure_ascii=False)

        with self._conn() as conn:
            conn.execute(
                """
                UPDATE daily_topic_progress
                SET daily_score = ?,
                    daily_game_scores_json = ?
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (int(total), scores_json, learner_id, day_iso, language, topic_key),
            )
        logger.info(
            "daily_score_saved learner_id=%s day=%s language=%s topic=%s total=%s game_type=%s game_score=%s",
            learner_id,
            day_iso,
            language,
            topic_key,
            total,
            game_type,
            normalized_score,
        )
        return DailyTopicProgress(
            learner_id=progress.learner_id,
            day_iso=progress.day_iso,
            language=progress.language,
            topic_key=progress.topic_key,
            lesson_completed=progress.lesson_completed,
            completed_daily_games_json=progress.completed_daily_games_json,
            level_state=progress.level_state,
            daily_score=int(total),
            daily_game_scores_json=scores_json,
            daily_game_failures_json=progress.daily_game_failures_json,
        )

    def increment_daily_game_failure(
        self,
        learner_id: str,
        day_iso: str,
        language: str,
        topic_key: str,
        game_type: str,
        increment: int = 1,
    ) -> DailyTopicProgress:
        progress = self.load_or_create_daily_topic_progress(
            learner_id=learner_id,
            day_iso=day_iso,
            language=language,
            topic_key=topic_key,
        )
        amount = max(1, int(increment))
        failures = progress.daily_game_failures()
        failures[game_type] = int(failures.get(game_type, 0)) + amount
        failures_json = json.dumps(failures, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE daily_topic_progress
                SET daily_game_failures_json = ?
                WHERE learner_id = ? AND day_iso = ? AND language = ? AND topic_key = ?
                """,
                (failures_json, learner_id, day_iso, language, topic_key),
            )
        logger.info(
            "daily_game_failure_saved learner_id=%s day=%s language=%s topic=%s game_type=%s total_failures=%s",
            learner_id,
            day_iso,
            language,
            topic_key,
            game_type,
            failures[game_type],
        )
        return DailyTopicProgress(
            learner_id=progress.learner_id,
            day_iso=progress.day_iso,
            language=progress.language,
            topic_key=progress.topic_key,
            lesson_completed=progress.lesson_completed,
            completed_daily_games_json=progress.completed_daily_games_json,
            level_state=progress.level_state,
            daily_score=progress.daily_score,
            daily_game_scores_json=progress.daily_game_scores_json,
            daily_game_failures_json=failures_json,
        )

    def aggregate_topic_failures(self, learner_id: str, language: str, topic_key: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT daily_game_failures_json
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND topic_key = ?
                """,
                (learner_id, language, topic_key),
            ).fetchall()
        for row in rows:
            raw = str(row[0] or "").strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for game_type, value in parsed.items():
                try:
                    totals[str(game_type)] = int(totals.get(str(game_type), 0)) + int(value)
                except (TypeError, ValueError):
                    continue
        return totals

    def count_days_on_topic(self, learner_id: str, language: str, topic_key: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND topic_key = ?
                """,
                (learner_id, language, topic_key),
            ).fetchone()
        return int(row[0] if row else 0)

    def count_high_score_days(self, learner_id: str, language: str, threshold: int = 240) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND daily_score >= ?
                """,
                (learner_id, language, int(threshold)),
            ).fetchone()
        return int(row[0] if row else 0)

    def recent_topic_scores(self, learner_id: str, language: str, topic_key: str, limit: int = 5) -> list[int]:
        normalized_limit = max(1, int(limit))
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT daily_score
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND topic_key = ?
                ORDER BY day_iso DESC
                LIMIT ?
                """,
                (learner_id, language, topic_key, normalized_limit),
            ).fetchall()
        return [int(row[0] or 0) for row in rows]

    def latest_daily_topic_progress_before(
        self,
        *,
        learner_id: str,
        language: str,
        before_day_iso: str,
    ) -> DailyTopicProgress | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT learner_id, day_iso, language, topic_key, lesson_completed, completed_daily_games_json,
                       level_state, daily_score, daily_game_scores_json, daily_game_failures_json
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND day_iso < ?
                ORDER BY day_iso DESC
                LIMIT 1
                """,
                (learner_id, language, before_day_iso),
            ).fetchone()
        if not row:
            return None
        logger.debug(
            "daily_topic_progress_previous_loaded learner_id=%s before_day=%s language=%s actual_day=%s topic=%s",
            learner_id,
            before_day_iso,
            language,
            row[1],
            row[3],
        )
        return DailyTopicProgress(*row)

    def retention_ratio(
        self,
        learner_id: str,
        language: str,
        topic_key: str,
        current_day_iso: str,
        gap_days: int = 3,
    ) -> float | None:
        try:
            current_day = date.fromisoformat(current_day_iso)
        except ValueError:
            return None
        cutoff = (current_day - timedelta(days=max(1, gap_days))).isoformat()

        with self._conn() as conn:
            current_row = conn.execute(
                """
                SELECT day_iso, daily_score
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND topic_key = ? AND day_iso <= ?
                ORDER BY day_iso DESC
                LIMIT 1
                """,
                (learner_id, language, topic_key, current_day_iso),
            ).fetchone()
            if not current_row:
                return None
            previous_row = conn.execute(
                """
                SELECT day_iso, daily_score
                FROM daily_topic_progress
                WHERE learner_id = ? AND language = ? AND topic_key = ? AND day_iso <= ?
                ORDER BY day_iso DESC
                LIMIT 1
                """,
                (learner_id, language, topic_key, cutoff),
            ).fetchone()

        if not previous_row:
            return None
        current_score = float(current_row[1] or 0)
        previous_score = float(previous_row[1] or 0)
        if previous_score <= 0:
            return None
        ratio = max(0.0, min(200.0, (current_score / previous_score) * 100.0))
        return round(ratio, 1)

    def load_or_create_assessment_state(self, learner_id: str) -> LearnerAssessmentState:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT learner_id, weekly_exam_last_day_iso, weekly_exam_passed_count, level_exams_passed_json
                FROM learner_assessment_state
                WHERE learner_id = ?
                """,
                (learner_id,),
            ).fetchone()
            if row:
                return LearnerAssessmentState(*row)
            conn.execute(
                """
                INSERT INTO learner_assessment_state (
                    learner_id, weekly_exam_last_day_iso, weekly_exam_passed_count, level_exams_passed_json
                )
                VALUES (?, '', 0, '{}')
                """,
                (learner_id,),
            )
        logger.info("assessment_state_created learner_id=%s", learner_id)
        return LearnerAssessmentState(
            learner_id=learner_id,
            weekly_exam_last_day_iso="",
            weekly_exam_passed_count=0,
            level_exams_passed_json="{}",
        )

    def save_weekly_exam_result(self, learner_id: str, day_iso: str, passed: bool) -> LearnerAssessmentState:
        state = self.load_or_create_assessment_state(learner_id)
        passed_count = int(state.weekly_exam_passed_count) + (1 if passed else 0)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_assessment_state
                SET weekly_exam_last_day_iso = ?,
                    weekly_exam_passed_count = ?
                WHERE learner_id = ?
                """,
                (day_iso, passed_count, learner_id),
            )
        logger.info(
            "weekly_exam_saved learner_id=%s day=%s passed=%s passed_count=%s",
            learner_id,
            day_iso,
            passed,
            passed_count,
        )
        return LearnerAssessmentState(
            learner_id=learner_id,
            weekly_exam_last_day_iso=day_iso,
            weekly_exam_passed_count=passed_count,
            level_exams_passed_json=state.level_exams_passed_json,
        )

    def mark_level_exam_passed(self, learner_id: str, language: str, from_level: int, to_level: int) -> LearnerAssessmentState:
        state = self.load_or_create_assessment_state(learner_id)
        passed_map = state.level_exams_passed()
        key = f"{language}:{from_level}->{to_level}"
        passed_map[key] = 1
        passed_json = json.dumps(passed_map, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE learner_assessment_state
                SET level_exams_passed_json = ?
                WHERE learner_id = ?
                """,
                (passed_json, learner_id),
            )
        logger.info(
            "level_exam_marked learner_id=%s transition=%s",
            learner_id,
            key,
        )
        return LearnerAssessmentState(
            learner_id=state.learner_id,
            weekly_exam_last_day_iso=state.weekly_exam_last_day_iso,
            weekly_exam_passed_count=state.weekly_exam_passed_count,
            level_exams_passed_json=passed_json,
        )

    def level_exam_passed(self, learner_id: str, language: str, from_level: int, to_level: int) -> bool:
        state = self.load_or_create_assessment_state(learner_id)
        key = f"{language}:{from_level}->{to_level}"
        return int(state.level_exams_passed().get(key, 0)) > 0

    def mark_topic_closed(
        self,
        learner_id: str,
        language: str,
        topic_key: str,
        closed_day_iso: str,
        closed_level: int,
        reason: str,
    ) -> None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT closed_level
                FROM closed_topics
                WHERE learner_id = ? AND language = ? AND topic_key = ?
                """,
                (learner_id, language, topic_key),
            ).fetchone()
            if row:
                next_level = max(int(row[0]), int(closed_level))
                conn.execute(
                    """
                    UPDATE closed_topics
                    SET closed_day_iso = ?, closed_level = ?, reason = ?
                    WHERE learner_id = ? AND language = ? AND topic_key = ?
                    """,
                    (closed_day_iso, next_level, reason, learner_id, language, topic_key),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO closed_topics (
                        learner_id, language, topic_key, closed_day_iso, closed_level, reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (learner_id, language, topic_key, closed_day_iso, int(closed_level), reason),
                )
        logger.info(
            "topic_closed_saved learner_id=%s language=%s topic=%s level=%s reason=%s",
            learner_id,
            language,
            topic_key,
            closed_level,
            reason,
        )

    def list_closed_topics(self, learner_id: str, language: str) -> list[ClosedTopic]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT learner_id, language, topic_key, closed_day_iso, closed_level, reason
                FROM closed_topics
                WHERE learner_id = ? AND language = ?
                ORDER BY closed_day_iso DESC
                """,
                (learner_id, language),
            ).fetchall()
        return [ClosedTopic(*row) for row in rows]

    def count_closed_topics(self, learner_id: str, language: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM closed_topics
                WHERE learner_id = ? AND language = ?
                """,
                (learner_id, language),
            ).fetchone()
        return int(row[0] if row else 0)

    def load_item_review_state(
        self,
        learner_id: str,
        language: str,
        topic_key: str,
        game_type: str,
        item_id: str,
    ) -> ItemReviewState | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT learner_id, language, topic_key, game_type, item_id, due_day_iso,
                       interval_days, ease, repetitions, lapses, last_score, last_seen_day_iso
                FROM item_review_state
                WHERE learner_id = ? AND language = ? AND topic_key = ? AND game_type = ? AND item_id = ?
                """,
                (learner_id, language, topic_key, game_type, item_id),
            ).fetchone()
        if row is None:
            return None
        return ItemReviewState(*row)

    def upsert_item_review_state(
        self,
        learner_id: str,
        language: str,
        topic_key: str,
        game_type: str,
        item_id: str,
        due_day_iso: str,
        interval_days: int,
        ease: float,
        repetitions: int,
        lapses: int,
        last_score: int,
        last_seen_day_iso: str,
    ) -> ItemReviewState:
        payload = (
            learner_id,
            language,
            topic_key,
            game_type,
            item_id,
            due_day_iso,
            int(max(1, interval_days)),
            float(max(1.3, ease)),
            int(max(0, repetitions)),
            int(max(0, lapses)),
            int(max(0, min(100, last_score))),
            last_seen_day_iso,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO item_review_state (
                    learner_id, language, topic_key, game_type, item_id, due_day_iso,
                    interval_days, ease, repetitions, lapses, last_score, last_seen_day_iso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (learner_id, language, topic_key, game_type, item_id)
                DO UPDATE SET
                    due_day_iso = excluded.due_day_iso,
                    interval_days = excluded.interval_days,
                    ease = excluded.ease,
                    repetitions = excluded.repetitions,
                    lapses = excluded.lapses,
                    last_score = excluded.last_score,
                    last_seen_day_iso = excluded.last_seen_day_iso
                """,
                payload,
            )
        logger.info(
            "item_review_state_saved learner_id=%s language=%s topic=%s game_type=%s item_id=%s due=%s interval=%s reps=%s lapses=%s score=%s ease=%.2f",
            learner_id,
            language,
            topic_key,
            game_type,
            item_id,
            due_day_iso,
            int(max(1, interval_days)),
            int(max(0, repetitions)),
            int(max(0, lapses)),
            int(max(0, min(100, last_score))),
            float(max(1.3, ease)),
        )
        return ItemReviewState(*payload)

    def list_completed_extra_game_types_for_day(
        self,
        *,
        learner_id: str,
        language: str,
        topic_key: str,
        day_iso: str,
        excluded_game_types: list[str],
    ) -> list[str]:
        excluded = [str(value).strip() for value in excluded_game_types if str(value).strip()]
        with self._conn() as conn:
            if excluded:
                placeholders = ",".join("?" for _ in excluded)
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT game_type
                    FROM item_review_state
                    WHERE learner_id = ?
                      AND language = ?
                      AND topic_key = ?
                      AND last_seen_day_iso = ?
                      AND game_type NOT IN ({placeholders})
                    ORDER BY game_type ASC
                    """,
                    (learner_id, language, topic_key, day_iso, *excluded),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT game_type
                    FROM item_review_state
                    WHERE learner_id = ?
                      AND language = ?
                      AND topic_key = ?
                      AND last_seen_day_iso = ?
                    ORDER BY game_type ASC
                    """,
                    (learner_id, language, topic_key, day_iso),
                ).fetchall()
        return [str(row[0]).strip() for row in rows if str(row[0]).strip()]

    def list_due_item_review_states(
        self,
        learner_id: str,
        language: str,
        current_day_iso: str,
        limit: int = 50,
        topic_key: str | None = None,
    ) -> list[ItemReviewState]:
        max_items = max(1, int(limit))
        with self._conn() as conn:
            if topic_key:
                rows = conn.execute(
                    """
                    SELECT learner_id, language, topic_key, game_type, item_id, due_day_iso,
                           interval_days, ease, repetitions, lapses, last_score, last_seen_day_iso
                    FROM item_review_state
                    WHERE learner_id = ? AND language = ? AND topic_key = ? AND due_day_iso <= ?
                    ORDER BY due_day_iso ASC, topic_key ASC, game_type ASC, item_id ASC
                    LIMIT ?
                    """,
                    (learner_id, language, topic_key, current_day_iso, max_items),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT learner_id, language, topic_key, game_type, item_id, due_day_iso,
                           interval_days, ease, repetitions, lapses, last_score, last_seen_day_iso
                    FROM item_review_state
                    WHERE learner_id = ? AND language = ? AND due_day_iso <= ?
                    ORDER BY due_day_iso ASC, topic_key ASC, game_type ASC, item_id ASC
                    LIMIT ?
                    """,
                    (learner_id, language, current_day_iso, max_items),
                ).fetchall()
        return [ItemReviewState(*row) for row in rows]
