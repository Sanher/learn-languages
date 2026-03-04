from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import date, datetime, timedelta
from math import log2
from pathlib import Path
from random import Random
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from language_games.orchestrator import GamesOrchestrator
from language_games.services import (
    ALIAS_GAME_TYPE_KANA_SPEED_ROUND,
    GAME_TYPE_CONTEXT_QUIZ,
    GAME_TYPE_GRAMMAR_PARTICLE_FIX,
    GAME_TYPE_KANJI_MATCH,
    GAME_TYPE_LISTENING_GAP_FILL,
    GAME_TYPE_MORA_ROMANIZATION,
    GAME_TYPE_PRONUNCIATION_MATCH,
    GAME_TYPE_SENTENCE_ORDER,
    ContextQuizAttempt,
    ContextQuizService,
    GrammarParticleAttempt,
    GrammarParticleFixService,
    KanaSpeedRoundService,
    KanjiMatchAttempt,
    KanjiMatchService,
    ListeningGapFillAttempt,
    ListeningGapFillService,
    MoraRomanizationAttempt,
    MoraRomanizationService,
    PronunciationMatchAttempt,
    PronunciationMatchService,
    ScriptSpeedAttempt,
    SentenceOrderAttempt,
    SentenceOrderService,
)
from language_games.services.registry import GameServiceRegistry
from .game_engine import DailyGamePlanner, LearnerSnapshot
from .memory import ItemReviewState, ProgressMemory
from .services.elevenlabs_client import ElevenLabsService
from .services.openai_client import OpenAIPlanner
from .topic_flow import TOPICS_BY_LANGUAGE, TopicDefinition, topic_for_day

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
ADDON_LANGUAGE_DATA_DIR = Path("/data") / "japanese"
LOCAL_LANGUAGE_DATA_DIR = BASE_DIR / "data" / "japanese"
DB_PATH = str((ADDON_LANGUAGE_DATA_DIR if Path("/data").exists() else LOCAL_LANGUAGE_DATA_DIR) / "progress.db")
DEFAULT_LEARNER_ID = os.getenv("HA_DEFAULT_LEARNER_ID", "ha_default_user")
AVAILABLE_LANGUAGES = ["ja"]
AVAILABLE_SECONDARY_TRANSLATION_LANGUAGES = {"es": "Español"}
TRANSLATABLE_STRING_FIELDS = {
    "title",
    "prompt",
    "objective",
    "description",
    "topic_description",
    "example_literal_translation",
    "literal_translation",
    "translation_hint",
    "feedback",
    "topic_days_message",
    "context_prompt",
    "ai_generated_prompt",
    "expected_translation",
    "recognized_translation",
}
TRANSLATABLE_LIST_FIELDS = {
    "theory_points",
    "feedback",
}
SRS_DEFAULT_EASE = 2.5
SRS_MIN_EASE = 1.3
SRS_MAX_INTERVAL_DAYS = 3650
WEEKLY_EXAM_MODE = os.getenv("LEARN_LANGUAGES_WEEKLY_EXAM_MODE", "legacy").strip().lower()
WEEKLY_EXAM_FORCE_LEGACY = WEEKLY_EXAM_MODE != "cumulative"
GAME_NAME_ALIASES = {
    GAME_TYPE_KANJI_MATCH: "Kanji Match",
    ALIAS_GAME_TYPE_KANA_SPEED_ROUND: "Kana Speed Round",
    GAME_TYPE_GRAMMAR_PARTICLE_FIX: "Grammar Particle Fix",
    GAME_TYPE_SENTENCE_ORDER: "Sentence Order",
    GAME_TYPE_MORA_ROMANIZATION: "Mora Romanization",
    GAME_TYPE_LISTENING_GAP_FILL: "Listening Gap Fill",
    GAME_TYPE_PRONUNCIATION_MATCH: "Guided Pronunciation",
    GAME_TYPE_CONTEXT_QUIZ: "Context Quiz",
}

app = FastAPI(title="Japanese Daily Trainer")

# Dedicated logger so HA shows endpoint traces with timestamps.
logger = logging.getLogger("learn_languages.japanese.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

planner = DailyGamePlanner()
memory = ProgressMemory(DB_PATH)
openai_planner = OpenAIPlanner()
elevenlabs = ElevenLabsService()
registry = GameServiceRegistry()
game_services: dict[str, Any] = {}
logger.info(
    "provider_config openai_key=%s openai_model=%s elevenlabs_key=%s elevenlabs_voice_id=%s elevenlabs_model_id=%s weekly_exam_mode=%s",
    bool(openai_planner.api_key),
    openai_planner.model,
    bool(elevenlabs.api_key),
    bool(elevenlabs.voice_id),
    elevenlabs.model_id,
    "legacy" if WEEKLY_EXAM_FORCE_LEGACY else "cumulative",
)


def _register_game(service: Any) -> None:
    registry.register(service)
    game_services[service.game_type] = service


_register_game(KanjiMatchService())
_register_game(KanaSpeedRoundService())
_register_game(GrammarParticleFixService())
_register_game(SentenceOrderService())
_register_game(MoraRomanizationService())
_register_game(ListeningGapFillService())
_register_game(PronunciationMatchService())
_register_game(ContextQuizService())

orchestrator = GamesOrchestrator(registry=registry)


class DailyRequest(BaseModel):
    learner_id: str
    note: str = ""


class DailyGamesRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    level_override_today: int | None = Field(default=None, ge=1, le=3)


class DailyLessonCompleteRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str = "ja"
    topic_key: str | None = None


class ExtraGameLoadRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    game_type: str
    language: str = "ja"
    topic_key: str | None = None


class WeeklyExamRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str = "ja"
    topic_key: str | None = None
    mode: str | None = None
    exam_score: int | None = Field(default=None, ge=0, le=300)
    question_count: int = Field(default=10, ge=3, le=20)
    answers: list[dict[str, Any]] = Field(default_factory=list)


class LevelExamRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str = "ja"
    target_level: int | None = Field(default=None, ge=2, le=3)
    exam_score: int | None = Field(default=None, ge=0, le=300)


class ClosedTopicsRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str = "ja"


class TopicReviewRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str = "ja"
    topic_key: str


class LanguageUpdateRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str


class SecondaryTranslationUpdateRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    secondary_language: str | None = None


class SessionResult(BaseModel):
    learner_id: str
    accuracy: float
    streak_days: int
    games_done: list[str]


class PronunciationRequest(BaseModel):
    expected: str
    transcript: str


class TextToSpeechRequest(BaseModel):
    text: str
    language: str = "ja"
    play_count: int = Field(default=0, ge=0)


class GameEvaluateRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    game_type: str
    language: str = "ja"
    level: int = 1
    retry_count: int = 0
    review_mode: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        started = perf_counter()
        logger.info("REQ method=%s path=%s", request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (perf_counter() - started) * 1000
            logger.exception("ERR method=%s path=%s elapsed_ms=%.1f", request.method, request.url.path, elapsed_ms)
            raise
        elapsed_ms = (perf_counter() - started) * 1000
        logger.info("RES method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
        return response
    return await call_next(request)


def _resolve_web_asset(path: str) -> Path:
    web_root = WEB_DIR.resolve()
    candidate = (WEB_DIR / str(path or "")).resolve()
    # Do not allow path traversal outside /web.
    if candidate != web_root and web_root not in candidate.parents:
        logger.warning("web_asset_traversal_blocked path=%s resolved=%s", path, candidate)
        raise HTTPException(status_code=404, detail="Not Found")
    if not candidate.exists() or not candidate.is_file():
        logger.info("web_asset_not_found path=%s resolved=%s", path, candidate)
        raise HTTPException(status_code=404, detail="Not Found")
    return candidate


@app.get("/health")
def health() -> dict[str, Any]:
    db_file = Path(DB_PATH)
    return {
        "status": "ok",
        "providers": {
            "openai_configured": bool(openai_planner.api_key),
            "elevenlabs_configured": bool(elevenlabs.api_key and elevenlabs.voice_id),
        },
        "storage": {
            "db_exists": db_file.exists(),
            "db_writable_parent": db_file.parent.exists() and os.access(db_file.parent, os.W_OK),
        },
    }


@app.get("/web/")
def web_index() -> FileResponse:
    return FileResponse(_resolve_web_asset("index.html"))


@app.get("/web/{path:path}")
def web_assets(path: str) -> FileResponse:
    return FileResponse(_resolve_web_asset(path))


@app.get("/")
def root_index() -> FileResponse:
    return FileResponse(_resolve_web_asset("index.html"))


@app.get("/app.js")
def root_app_js() -> FileResponse:
    return FileResponse(_resolve_web_asset("app.js"))


@app.get("/styles.css")
def root_styles_css() -> FileResponse:
    return FileResponse(_resolve_web_asset("styles.css"))


@app.post("/api/daily")
async def get_daily_plan(req: DailyRequest) -> dict:
    logger.info("daily_plan learner_id=%s note_len=%s", req.learner_id, len(req.note or ""))
    state = memory.load_or_create(req.learner_id)
    snapshot = LearnerSnapshot(
        learner_id=state.learner_id,
        streak_days=state.streak_days,
        recent_accuracy=state.recent_accuracy,
        recent_games=[g for g in state.recent_games_csv.split(",") if g],
    )

    games = planner.choose_games(snapshot, date.today())
    difficulty = planner.difficulty_for(snapshot)
    content = await openai_planner.generate_daily_content(
        difficulty=difficulty,
        games=games,
        learner_note=req.note,
    )

    return {
        "games": games,
        "difficulty": difficulty,
        "content": content,
    }


def _service_level_from_difficulty(difficulty: int) -> int:
    if difficulty <= 3:
        return 1
    if difficulty <= 6:
        return 2
    return 3


def _normalize_secondary_language(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if not normalized or normalized in {"off", "none", "null"}:
        return None
    if normalized not in AVAILABLE_SECONDARY_TRANSLATION_LANGUAGES:
        return None
    return normalized


def _translation_preferences_payload(secondary_language: str | None) -> dict[str, Any]:
    normalized = _normalize_secondary_language(secondary_language)
    options = [{"code": code, "label": label} for code, label in AVAILABLE_SECONDARY_TRANSLATION_LANGUAGES.items()]
    return {
        "primary_translation_language": "en",
        "secondary_translation_language": normalized,
        "available_secondary_translation_languages": options,
        "secondary_translation_provider_available": bool(openai_planner.api_key),
    }


def _translation_cache_key(*, source_text: str, source_language: str, target_language: str, context: str) -> str:
    material = f"{source_language}|{target_language}|{context}|{source_text}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _secondary_translation_for_text(
    *,
    text: str,
    secondary_language: str | None,
    context: str,
    memo: dict[tuple[str, str, str], str | None],
) -> str | None:
    normalized_secondary = _normalize_secondary_language(secondary_language)
    source_text = str(text or "").strip()
    if not normalized_secondary or not source_text:
        return None
    if not openai_planner.api_key:
        return None

    memo_key = (normalized_secondary, context, source_text)
    if memo_key in memo:
        return memo[memo_key]

    cache_key = _translation_cache_key(
        source_text=source_text,
        source_language="en",
        target_language=normalized_secondary,
        context=context,
    )
    cached = memory.load_cached_translation(cache_key)
    if cached is not None:
        logger.info("translation_cache_hit target=%s context=%s", normalized_secondary, context)
        memo[memo_key] = cached
        return cached

    logger.info("translation_cache_miss target=%s context=%s", normalized_secondary, context)
    translation_result = openai_planner.translate_text(
        source_text=source_text,
        source_language="en",
        target_language=normalized_secondary,
        context=context,
    )
    translated_text = str(translation_result.get("translated_text") or "").strip()
    if translated_text:
        memory.save_cached_translation(
            cache_key=cache_key,
            source_text=source_text,
            source_language="en",
            target_language=normalized_secondary,
            context=context,
            translated_text=translated_text,
            updated_at_iso=datetime.utcnow().isoformat(),
        )
        memo[memo_key] = translated_text
        return translated_text

    logger.warning(
        "translation_unavailable target=%s context=%s detail=%s",
        normalized_secondary,
        context,
        translation_result.get("error", "unknown"),
    )
    memo[memo_key] = None
    return None


def _translation_bundle_for_text(
    *,
    text: str,
    secondary_language: str | None,
    context: str,
    memo: dict[tuple[str, str, str], str | None],
) -> dict[str, Any]:
    en_text = str(text or "").strip()
    normalized_secondary = _normalize_secondary_language(secondary_language)
    return {
        "en": en_text,
        "secondary_lang": normalized_secondary,
        "secondary": _secondary_translation_for_text(
            text=en_text,
            secondary_language=normalized_secondary,
            context=context,
            memo=memo,
        ),
    }


def _augment_with_secondary_translations(
    value: Any,
    *,
    secondary_language: str | None,
    context: str,
    memo: dict[tuple[str, str, str], str | None],
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, inner in value.items():
            field_context = f"{context}.{key}" if context else str(key)
            result[key] = _augment_with_secondary_translations(
                inner,
                secondary_language=secondary_language,
                context=field_context,
                memo=memo,
            )

        for key in list(value.keys()):
            inner = value.get(key)
            field_context = f"{context}.{key}" if context else str(key)
            if key in TRANSLATABLE_STRING_FIELDS and isinstance(inner, str):
                result[f"{key}_translations"] = _translation_bundle_for_text(
                    text=inner,
                    secondary_language=secondary_language,
                    context=field_context,
                    memo=memo,
                )
            elif key in TRANSLATABLE_LIST_FIELDS and isinstance(inner, list) and all(isinstance(item, str) for item in inner):
                result[f"{key}_translations"] = [
                    _translation_bundle_for_text(
                        text=item,
                        secondary_language=secondary_language,
                        context=f"{field_context}[{idx}]",
                        memo=memo,
                    )
                    for idx, item in enumerate(inner)
                ]
        return result

    if isinstance(value, list):
        return [
            _augment_with_secondary_translations(
                item,
                secondary_language=secondary_language,
                context=f"{context}[{idx}]",
                memo=memo,
            )
            for idx, item in enumerate(value)
        ]

    return value


def _secondary_translation_for_learner(learner_id: str) -> str | None:
    prefs = memory.load_or_create_preferences(learner_id)
    return _normalize_secondary_language(prefs.secondary_translation_language())


def _translate_response_for_learner(
    *,
    learner_id: str,
    payload: dict[str, Any],
    context: str,
) -> dict[str, Any]:
    secondary_language = _secondary_translation_for_learner(learner_id)
    return _augment_with_secondary_translations(
        payload,
        secondary_language=secondary_language,
        context=context,
        memo={},
    )


def _ui_state(
    learner_id: str,
    preferred_language: str,
    difficulty: int,
    today_level: int,
    overridden: bool,
    secondary_translation_language: str | None = None,
) -> dict[str, Any]:
    current_level = memory.level_for_language(learner_id, preferred_language, default_level=1)
    return {
        "learner_id": learner_id,
        "language": preferred_language,
        "available_languages": AVAILABLE_LANGUAGES,
        "difficulty": difficulty,
        "current_level": current_level,
        "today_level": today_level,
        "today_level_overridden": overridden,
        # UI contract: app strings stay in English, this controls optional secondary translation lines.
        "translation_preferences": _translation_preferences_payload(secondary_translation_language),
    }


def _choose_single_game(games: list[str], available_games: list[str], learner_id: str, language: str, today_level: int) -> str | None:
    if not available_games:
        return None
    seed = f"{learner_id}:{date.today().isoformat()}:{language}:{today_level}:{','.join(games)}"
    rnd = Random(seed)
    return available_games[rnd.randrange(len(available_games))]


def _daily_progress_payload(progress, daily_game_types: list[str]) -> dict[str, Any]:
    completed = [game for game in progress.completed_daily_games() if game in daily_game_types]
    total_required = len(daily_game_types)
    extras_unlocked = bool(progress.lesson_completed) and len(completed) >= total_required
    score_map = {game: int(progress.daily_game_scores().get(game, 0)) for game in daily_game_types}
    return {
        "topic_key": progress.topic_key,
        "lesson_completed": bool(progress.lesson_completed),
        "completed_daily_games": completed,
        "daily_games_required": daily_game_types,
        "daily_games_completed_count": len(completed),
        "daily_games_total": total_required,
        "level_state": int(progress.level_state),
        "daily_score": int(progress.daily_score),
        "daily_score_max": 300,
        "daily_scores_by_game": score_map,
        "extras_unlocked": extras_unlocked,
    }


def _learning_contract_payload(*, daily_required_games: int) -> dict[str, Any]:
    return {
        "daily_required_games": int(daily_required_games),
        "daily_score_cap": 300,
        "srs_mode": "item_sm2_lite",
        "srs_tracking_enabled": True,
    }


def _daily_topic_for(learner_id: str, language: str) -> tuple[TopicDefinition, Any, str]:
    today = date.today()
    topic = topic_for_day(learner_id=learner_id, language=language, target_day=today)
    progress = memory.load_or_create_daily_topic_progress(
        learner_id=learner_id,
        day_iso=today.isoformat(),
        language=language,
        topic_key=topic.topic_key,
    )
    return topic, progress, today.isoformat()


def _topic_lesson_payload(topic: TopicDefinition, level: int, secondary_translation_language: str | None = None) -> dict[str, Any]:
    lesson = topic.lesson_for_level(level)
    payload = {
        "topic_key": topic.topic_key,
        "topic_title": topic.title,
        "topic_description": topic.description,
        "level": level,
        "title": lesson.title,
        "objective": lesson.objective,
        "theory_points": list(lesson.theory_points),
        "example_script": lesson.example_script,
        "example_romanized": lesson.example_romanized,
        "example_literal_translation": lesson.example_literal_translation,
    }
    return _augment_with_secondary_translations(
        payload,
        secondary_language=secondary_translation_language,
        context=f"lesson.{topic.topic_key}.level{level}",
        memo={},
    )


def _target_score_for_topic_day(topic_day_index: int) -> int:
    # Logarithmic progression: day 1 -> 150, day 2 -> ~180, then slower growth.
    normalized_day = max(1, int(topic_day_index))
    target = 150 + (30 * log2(normalized_day))
    return int(min(300, round(target)))


def _weekly_exam_due(last_exam_day_iso: str | None, today_iso: str) -> bool:
    if not last_exam_day_iso:
        return True
    try:
        last_day = date.fromisoformat(last_exam_day_iso)
        today = date.fromisoformat(today_iso)
    except ValueError:
        return True
    return (today - last_day) >= timedelta(days=7)


def _level_exam_flags(
    *,
    current_level: int,
    weekly_passed_count: int,
    high_score_days: int,
    retention_ratio: float | None,
    topic_failures: dict[str, int],
    level_1_to_2_passed: bool,
    level_2_to_3_passed: bool,
) -> dict[str, bool]:
    failure_total = sum(int(value) for value in topic_failures.values())
    ready_to_2 = (
        current_level == 1
        and not level_1_to_2_passed
        and weekly_passed_count >= 1
        and high_score_days >= 1
        and (retention_ratio is None or retention_ratio >= 70.0)
        and failure_total <= 12
    )
    ready_to_3 = (
        current_level == 2
        and not level_2_to_3_passed
        and weekly_passed_count >= 2
        and high_score_days >= 5
        and (retention_ratio is not None and retention_ratio >= 80.0)
        and failure_total <= 8
    )
    return {
        "ready_to_level_2": bool(ready_to_2),
        "ready_to_level_3": bool(ready_to_3),
    }


def _topic_title(language: str, topic_key: str) -> str:
    for topic in TOPICS_BY_LANGUAGE.get(language, ()):
        if topic.topic_key == topic_key:
            return topic.title
    return topic_key


def _topic_definition_for_key(language: str, topic_key: str) -> TopicDefinition | None:
    normalized = str(topic_key or "").strip()
    if not normalized:
        return None
    for topic in TOPICS_BY_LANGUAGE.get(language, ()):
        if topic.topic_key == normalized:
            return topic
    return None


def _is_success_result(result: dict[str, Any]) -> bool | None:
    if "is_correct" in result:
        return bool(result.get("is_correct"))
    if "is_match" in result:
        return bool(result.get("is_match"))
    score = result.get("score")
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return None
    return numeric_score >= 80.0


def _srs_quality_from_score(score: int) -> int:
    normalized = max(0, min(100, int(score)))
    if normalized >= 90:
        return 5
    if normalized >= 80:
        return 4
    if normalized >= 65:
        return 3
    if normalized >= 50:
        return 2
    return 1


def _next_srs_state(previous: ItemReviewState | None, score: int) -> tuple[int, float, int, int, int]:
    raw_prev_interval = int(previous.interval_days) if previous is not None else 1
    prev_interval = raw_prev_interval
    prev_interval = max(1, min(SRS_MAX_INTERVAL_DAYS, prev_interval))
    if prev_interval != raw_prev_interval:
        logger.warning(
            "srs_interval_capped_previous raw=%s capped=%s max=%s",
            raw_prev_interval,
            prev_interval,
            SRS_MAX_INTERVAL_DAYS,
        )
    prev_ease = float(previous.ease) if previous is not None else SRS_DEFAULT_EASE
    prev_repetitions = int(previous.repetitions) if previous is not None else 0
    prev_lapses = int(previous.lapses) if previous is not None else 0
    quality = _srs_quality_from_score(score)

    if quality >= 3:
        repetitions = prev_repetitions + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 3
        else:
            interval = max(4, int(round(prev_interval * prev_ease)))
        ease_delta = 0.1 - ((5 - quality) * (0.08 + ((5 - quality) * 0.02)))
        ease = max(SRS_MIN_EASE, round(prev_ease + ease_delta, 2))
        lapses = prev_lapses
    else:
        repetitions = 0
        lapses = prev_lapses + 1
        interval = 1 if quality <= 1 else 2
        ease = max(SRS_MIN_EASE, round(prev_ease - 0.2, 2))

    raw_interval = int(interval)
    interval = max(1, min(SRS_MAX_INTERVAL_DAYS, raw_interval))
    if interval != raw_interval:
        logger.warning(
            "srs_interval_capped_next raw=%s capped=%s max=%s quality=%s",
            raw_interval,
            interval,
            SRS_MAX_INTERVAL_DAYS,
            quality,
        )
    return interval, ease, repetitions, lapses, quality


def _resolve_attempt_topic_key(learner_id: str, language: str, payload: dict[str, Any]) -> str | None:
    # Contract MVP (daily 3 games + extras): if topic is not explicit, bind attempt to today's active topic.
    explicit_topic = str(payload.get("topic_key", "")).strip()
    if explicit_topic:
        return explicit_topic
    try:
        today_topic = topic_for_day(learner_id=learner_id, language=language, target_day=date.today())
    except ValueError:
        return None
    return today_topic.topic_key


def _update_item_review_state(
    *,
    learner_id: str,
    language: str,
    game_type: str,
    item_id: str,
    payload: dict[str, Any],
    score: int,
) -> None:
    if language not in AVAILABLE_LANGUAGES:
        return
    topic_key = _resolve_attempt_topic_key(learner_id=learner_id, language=language, payload=payload)
    if not topic_key:
        logger.warning(
            "srs_update_skipped_missing_topic learner_id=%s language=%s game_type=%s item_id=%s",
            learner_id,
            language,
            game_type,
            item_id,
        )
        return
    today_iso = date.today().isoformat()
    previous = memory.load_item_review_state(
        learner_id=learner_id,
        language=language,
        topic_key=topic_key,
        game_type=game_type,
        item_id=item_id,
    )
    interval, ease, repetitions, lapses, quality = _next_srs_state(previous=previous, score=score)
    due_day_iso = (date.fromisoformat(today_iso) + timedelta(days=interval)).isoformat()
    memory.upsert_item_review_state(
        learner_id=learner_id,
        language=language,
        topic_key=topic_key,
        game_type=game_type,
        item_id=item_id,
        due_day_iso=due_day_iso,
        interval_days=interval,
        ease=ease,
        repetitions=repetitions,
        lapses=lapses,
        last_score=score,
        last_seen_day_iso=today_iso,
    )
    logger.info(
        "srs_update_done learner_id=%s language=%s topic=%s game_type=%s item_id=%s score=%s quality=%s due=%s interval=%s reps=%s lapses=%s ease=%.2f",
        learner_id,
        language,
        topic_key,
        game_type,
        item_id,
        int(score),
        quality,
        due_day_iso,
        interval,
        repetitions,
        lapses,
        ease,
    )


def _progress_insights(
    *,
    learner_id: str,
    language: str,
    topic_key: str,
    today_iso: str,
    current_level: int,
    daily_score: int,
) -> dict[str, Any]:
    topic_days_count = memory.count_days_on_topic(learner_id=learner_id, language=language, topic_key=topic_key)
    topic_day_target_score = _target_score_for_topic_day(topic_days_count)
    topic_day_target_reached = int(daily_score) >= int(topic_day_target_score)
    high_score_days_over_240 = memory.count_high_score_days(learner_id=learner_id, language=language, threshold=240)
    retention_ratio_percent = memory.retention_ratio(
        learner_id=learner_id,
        language=language,
        topic_key=topic_key,
        current_day_iso=today_iso,
        gap_days=3,
    )
    topic_failure_totals = memory.aggregate_topic_failures(
        learner_id=learner_id,
        language=language,
        topic_key=topic_key,
    )
    assessment = memory.load_or_create_assessment_state(learner_id)
    level_1_to_2_passed = memory.level_exam_passed(learner_id, language, from_level=1, to_level=2)
    level_2_to_3_passed = memory.level_exam_passed(learner_id, language, from_level=2, to_level=3)
    level_exam_ready_flags = _level_exam_flags(
        current_level=current_level,
        weekly_passed_count=int(assessment.weekly_exam_passed_count),
        high_score_days=high_score_days_over_240,
        retention_ratio=retention_ratio_percent,
        topic_failures=topic_failure_totals,
        level_1_to_2_passed=level_1_to_2_passed,
        level_2_to_3_passed=level_2_to_3_passed,
    )
    weekly_exam_due = _weekly_exam_due(assessment.weekly_exam_last_day_iso, today_iso=today_iso)
    closed_topics_count = memory.count_closed_topics(learner_id=learner_id, language=language)
    return {
        "topic_days_count": int(topic_days_count),
        "topic_days_message": f"You have worked on this topic for {topic_days_count} day(s).",
        "topic_day_target_score": int(topic_day_target_score),
        "topic_day_target_reached": bool(topic_day_target_reached),
        "high_score_days_over_240": int(high_score_days_over_240),
        "retention_ratio_percent": retention_ratio_percent,
        "topic_failure_totals": topic_failure_totals,
        "weekly_exam_due": bool(weekly_exam_due),
        "weekly_exam_last_day_iso": assessment.weekly_exam_last_day_iso,
        "weekly_exam_passed_count": int(assessment.weekly_exam_passed_count),
        "level_exam_passed_1_to_2": bool(level_1_to_2_passed),
        "level_exam_passed_2_to_3": bool(level_2_to_3_passed),
        "ready_to_level_2": bool(level_exam_ready_flags["ready_to_level_2"]),
        "ready_to_level_3": bool(level_exam_ready_flags["ready_to_level_3"]),
        "closed_topics_count": int(closed_topics_count),
    }


def _enrich_daily_progress_payload(
    *,
    learner_id: str,
    language: str,
    current_level: int,
    topic_key: str,
    today_iso: str,
    daily_progress: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(daily_progress)
    # Extra games are tracked independently from the 3 daily required games.
    # The UI uses this to inform the learner that extra practice does not affect daily score.
    daily_required_raw = daily_progress.get("daily_games_required", [])
    daily_required = sorted(
        {
            str(game_type).strip()
            for game_type in daily_required_raw
            if str(game_type).strip()
        }
    )
    extra_completed_types = memory.list_completed_extra_game_types_for_day(
        learner_id=learner_id,
        language=language,
        topic_key=topic_key,
        day_iso=today_iso,
        excluded_game_types=daily_required,
    )
    enriched["extra_games_completed_types"] = extra_completed_types
    enriched["extra_games_completed_count"] = len(extra_completed_types)
    enriched.update(
        _progress_insights(
            learner_id=learner_id,
            language=language,
            topic_key=topic_key,
            today_iso=today_iso,
            current_level=current_level,
            daily_score=int(daily_progress.get("daily_score", 0)),
        )
    )
    return enriched


def _extract_kana_sequence(prompt: str) -> str:
    for line in prompt.splitlines():
        if line.lower().startswith("read fast"):
            return line.split(":", 1)[1].strip() if ":" in line else line.strip()
    return prompt.strip()


def _game_payload(game_type: str, language: str, level: int, activity_id: str, prompt: str) -> dict[str, Any]:
    service = game_services.get(game_type)
    if service is None:
        return {}

    if game_type == GAME_TYPE_GRAMMAR_PARTICLE_FIX:
        items = service.get_items(language=language, level=level)
        item = next((it for it in items if it.item_id == activity_id), None)
        if item:
            return {
                "options": item.choices,
                "options_enriched": service.options_with_romaji(item.choices),
            }

    if game_type == GAME_TYPE_SENTENCE_ORDER:
        items = service.get_items(language=language, level=level)
        item = next((it for it in items if it.item_id == activity_id), None)
        if item:
            scrambled = item.ordered_tokens.copy()
            rnd = Random(item.item_id)
            rnd.shuffle(scrambled)
            if scrambled == item.ordered_tokens and len(scrambled) > 1:
                scrambled[0], scrambled[1] = scrambled[1], scrambled[0]
            return {
                "tokens_scrambled": scrambled,
                "ordered_tokens": item.ordered_tokens,
            }

    if game_type == GAME_TYPE_LISTENING_GAP_FILL:
        items = service.get_items(language=language, level=level)
        item = next((it for it in items if it.item_id == activity_id), None)
        if item:
            return {
                "tokens": item.tokens,
                "gap_positions": item.gap_positions,
                "options": item.options,
                "tts_text": item.script_line if language == "ja" else "",
            }

    if game_type == GAME_TYPE_MORA_ROMANIZATION:
        items = service.get_items(language=language, level=level)
        item = next((it for it in items if it.item_id == activity_id), None)
        if item:
            if level <= 1:
                mode = "beginner"
            elif level == 2:
                mode = "intermediate"
            else:
                mode = "advanced"
            payload = {
                "mode": mode,
                "mora_kana_tokens": item.mora_kana if mode in {"beginner", "intermediate"} else [],
                "mora_romaji_tokens": item.mora_romaji if mode in {"beginner", "intermediate"} else [],
                "japanese_text": item.japanese_text if mode == "advanced" else "",
                "literal_translation": item.literal_translation,
            }
            logger.info(
                "payload_mora_romanization_ready language=%s level=%s activity_id=%s mode=%s",
                language,
                level,
                activity_id,
                payload["mode"],
            )
            return payload
        logger.warning(
            "payload_mora_romanization_missing language=%s level=%s activity_id=%s",
            language,
            level,
            activity_id,
        )

    if game_type == GAME_TYPE_CONTEXT_QUIZ:
        items = service.get_items(language=language, level=level)
        item = next((it for it in items if it.item_id == activity_id), None)
        if item:
            return {
                "context_prompt": item.context_prompt,
                "options": service.options_for_ui(item.options),
            }

    if game_type == GAME_TYPE_KANJI_MATCH:
        pairs = service.get_pairs(language=language, level=level)
        view = service.build_attempt_view(language=language, level=level)
        return {
            "pairs": [
                {
                    "symbol": pair.symbol,
                    "meaning": pair.meaning,
                    "reading_romaji": pair.reading_romaji,
                }
                for pair in pairs
            ],
            "assistance_stage": view.get("assistance_stage"),
            "require_meaning_input": bool(view.get("require_meaning_input")),
        }

    if game_type == GAME_TYPE_PRONUNCIATION_MATCH:
        try:
            view = service.build_attempt_view(
                language=language,
                item_id=activity_id,
                level=level,
                show_translation=False,
            )
        except ValueError:
            logger.warning(
                "payload_pronunciation_item_missing language=%s level=%s activity_id=%s",
                language,
                level,
                activity_id,
            )
            view = {}
        return {
            "expected_text": prompt,
            "show_romanized_line": bool(view.get("show_romanized_line")),
            "romanized_line": view.get("romanized_line"),
        }

    if game_type == ALIAS_GAME_TYPE_KANA_SPEED_ROUND:
        sequence = _extract_kana_sequence(prompt)
        return {
            "expected_text": sequence,
            "tts_text": sequence,
        }

    return {}


def _build_card_for_activity(
    game_type: str,
    language: str,
    level: int,
    activity_id: str,
    secondary_translation_language: str | None = None,
) -> dict[str, Any] | None:
    service = game_services.get(game_type)
    if service is None:
        logger.warning("topic_card_missing_service game_type=%s", game_type)
        return None

    activities = service.get_activities(language=language, level=level)
    activity = next((item for item in activities if item.activity_id == activity_id), None)
    if activity is None:
        logger.warning(
            "topic_card_missing_activity game_type=%s language=%s level=%s activity_id=%s",
            game_type,
            language,
            level,
            activity_id,
        )
        return None

    payload = {
        "game_type": game_type,
        "display_name": GAME_NAME_ALIASES.get(game_type, game_type),
        "activity_id": activity.activity_id,
        "language": activity.language,
        "prompt": activity.prompt,
        "level": activity.level,
        "payload": _game_payload(
            game_type=game_type,
            language=language,
            level=level,
            activity_id=activity.activity_id,
            prompt=activity.prompt,
        ),
    }
    return _augment_with_secondary_translations(
        payload,
        secondary_language=secondary_translation_language,
        context=f"card.{game_type}.{activity.activity_id}",
        memo={},
    )


def _build_card_for_game_type(game_type: str, language: str, level: int, secondary_translation_language: str | None = None) -> dict[str, Any] | None:
    service = game_services.get(game_type)
    if service is None:
        return None
    activities = service.get_activities(language=language, level=level)
    if not activities:
        return None
    return _build_card_for_activity(
        game_type=game_type,
        language=language,
        level=level,
        activity_id=activities[0].activity_id,
        secondary_translation_language=secondary_translation_language,
    )


async def _attach_ai_prompts_to_cards(
    *,
    cards: list[dict[str, Any]],
    difficulty: int,
    learner_note: str,
    secondary_translation_language: str | None,
    context: str,
) -> None:
    if not cards or not openai_planner.api_key:
        return

    # Generate one prompt per game type (not per card instance) and reuse it for all cards of that type.
    requested_games: list[str] = []
    seen: set[str] = set()
    for card in cards:
        game_type = str(card.get("game_type") or "").strip()
        if not game_type or game_type in seen:
            continue
        seen.add(game_type)
        requested_games.append(game_type)
    if not requested_games:
        return

    try:
        generated = await openai_planner.generate_daily_content(
            difficulty=difficulty,
            games=requested_games,
            learner_note=learner_note,
        )
    except Exception as exc:  # pragma: no cover - defensive safety for provider/network issues
        logger.warning("ai_prompt_generation_failed context=%s detail=%s", context, type(exc).__name__)
        return

    source = str(generated.get("source") or "fallback").strip().lower()
    if source != "openai":
        logger.info("ai_prompt_generation_skipped context=%s source=%s", context, source or "fallback")
        return

    rows = generated.get("activities")
    if not isinstance(rows, list):
        logger.warning("ai_prompt_generation_invalid_payload context=%s", context)
        return

    prompts_by_game: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        game_type = str(row.get("game") or "").strip()
        prompt = str(row.get("prompt") or "").strip()
        if not game_type or not prompt or game_type in prompts_by_game:
            continue
        prompts_by_game[game_type] = prompt

    if not prompts_by_game:
        logger.warning("ai_prompt_generation_empty context=%s requested=%s", context, ",".join(requested_games))
        return

    # Shared translation memo to avoid repeated secondary-translation provider calls per response.
    memo: dict[tuple[str, str, str], str | None] = {}
    applied = 0
    for index, card in enumerate(cards):
        game_type = str(card.get("game_type") or "").strip()
        ai_prompt = prompts_by_game.get(game_type)
        if not ai_prompt:
            continue
        card["ai_generated_prompt"] = ai_prompt
        card["ai_prompt_source"] = "openai"
        cards[index] = _augment_with_secondary_translations(
            card,
            secondary_language=secondary_translation_language,
            context=f"{context}.{game_type}.{card.get('activity_id', '')}.ai_prompt",
            memo=memo,
        )
        applied += 1

    logger.info(
        "ai_prompt_generation_applied context=%s requested=%s applied=%s",
        context,
        len(requested_games),
        applied,
    )


def _build_card_for_activity_with_level_fallback(
    *,
    game_type: str,
    language: str,
    activity_id: str,
    preferred_level: int,
    secondary_translation_language: str | None = None,
) -> dict[str, Any] | None:
    levels: list[int] = [int(preferred_level), 1, 2, 3]
    seen: set[int] = set()
    for level in levels:
        if level in seen:
            continue
        seen.add(level)
        card = _build_card_for_activity(
            game_type=game_type,
            language=language,
            level=level,
            activity_id=activity_id,
            secondary_translation_language=secondary_translation_language,
        )
        if card is not None:
            return card
    return None


def _closed_topics_map(learner_id: str, language: str) -> dict[str, Any]:
    return {
        item.topic_key: item
        for item in memory.list_closed_topics(learner_id=learner_id, language=language)
    }


def _select_extra_card_for_game_type(
    *,
    learner_id: str,
    language: str,
    today_topic: TopicDefinition,
    today_level: int,
    game_type: str,
    today_iso: str,
    secondary_translation_language: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    closed_topics = _closed_topics_map(learner_id=learner_id, language=language)
    if closed_topics:
        due_items = memory.list_due_item_review_states(
            learner_id=learner_id,
            language=language,
            current_day_iso=today_iso,
            limit=120,
        )
        # Priority 1: due items from already closed topics.
        due_candidates = [
            item
            for item in due_items
            if item.game_type == game_type and item.topic_key in closed_topics
        ]
        due_candidates.sort(key=lambda item: (item.due_day_iso, -int(item.lapses), int(item.last_score)))
        for item in due_candidates:
            card = _build_card_for_activity_with_level_fallback(
                game_type=game_type,
                language=language,
                activity_id=item.item_id,
                preferred_level=today_level,
                secondary_translation_language=secondary_translation_language,
            )
            if card is None:
                continue
            card["topic_key"] = item.topic_key
            card["selection_source"] = "due_closed_topic"
            return card, "due_closed_topic"

    # Priority 2: weak game types for the current topic.
    failures = memory.aggregate_topic_failures(
        learner_id=learner_id,
        language=language,
        topic_key=today_topic.topic_key,
    )
    if int(failures.get(game_type, 0)) > 0:
        preferred_current = dict(today_topic.extra_plan_for_level(today_level)).get(game_type)
        if preferred_current:
            card = _build_card_for_activity(
                game_type=game_type,
                language=language,
                level=today_level,
                activity_id=preferred_current,
                secondary_translation_language=secondary_translation_language,
            )
            if card is not None:
                card["topic_key"] = today_topic.topic_key
                card["selection_source"] = "weak_current_topic"
                return card, "weak_current_topic"

    # Priority 3: default current-topic plan.
    topic_extra_map = dict(today_topic.extra_plan_for_level(today_level))
    preferred_activity_id = topic_extra_map.get(game_type)
    if preferred_activity_id:
        card = _build_card_for_activity(
            game_type=game_type,
            language=language,
            level=today_level,
            activity_id=preferred_activity_id,
            secondary_translation_language=secondary_translation_language,
        )
        if card is not None:
            card["topic_key"] = today_topic.topic_key
            card["selection_source"] = "current_topic_default"
            return card, "current_topic_default"

    fallback = _build_card_for_game_type(
        game_type=game_type,
        language=language,
        level=today_level,
        secondary_translation_language=secondary_translation_language,
    )
    if fallback is not None:
        fallback["topic_key"] = today_topic.topic_key
        fallback["selection_source"] = "current_generic_fallback"
        return fallback, "current_generic_fallback"
    return None, "missing"


def _exam_question_from_card(
    *,
    card: dict[str, Any],
    topic_key: str,
    topic_title: str,
    source: str,
) -> dict[str, Any]:
    payload = dict(card.get("payload") or {})
    payload.setdefault("item_id", card.get("activity_id", ""))
    return {
        "question_id": f"{topic_key}:{card.get('game_type', '')}:{card.get('activity_id', '')}",
        "topic_key": topic_key,
        "topic_title": topic_title,
        "source": source,
        "game_type": card.get("game_type"),
        "display_name": card.get("display_name"),
        "language": card.get("language"),
        "level": int(card.get("level", 1) or 1),
        "item_id": card.get("activity_id"),
        "prompt": card.get("prompt"),
        "payload": payload,
    }


def _weekly_exam_questions(
    *,
    learner_id: str,
    language: str,
    current_topic: TopicDefinition,
    current_level: int,
    today_iso: str,
    question_count: int,
) -> list[dict[str, Any]]:
    desired_count = max(3, int(question_count))
    closed_topics = _closed_topics_map(learner_id=learner_id, language=language)
    questions: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str, str]] = set()

    def _append_from_card(card: dict[str, Any] | None, topic_key: str, topic_title: str, source: str) -> None:
        if card is None:
            return
        key = (topic_key, str(card.get("game_type", "")), str(card.get("activity_id", "")))
        if key in seen_ids:
            return
        seen_ids.add(key)
        questions.append(
            _exam_question_from_card(
                card=card,
                topic_key=topic_key,
                topic_title=topic_title,
                source=source,
            )
        )

    # Closed-topic due items first (cumulative pressure).
    due_items = memory.list_due_item_review_states(
        learner_id=learner_id,
        language=language,
        current_day_iso=today_iso,
        limit=max(40, desired_count * 3),
    )
    due_items.sort(key=lambda item: (item.due_day_iso, -int(item.lapses), int(item.last_score)))
    for item in due_items:
        closed = closed_topics.get(item.topic_key)
        if closed is None:
            continue
        topic_def = _topic_definition_for_key(language=language, topic_key=item.topic_key)
        if topic_def is None:
            continue
        preferred_level = max(1, min(current_level, int(closed.closed_level)))
        card = _build_card_for_activity_with_level_fallback(
            game_type=item.game_type,
            language=language,
            activity_id=item.item_id,
            preferred_level=preferred_level,
        )
        _append_from_card(card, topic_def.topic_key, topic_def.title, "closed_due")
        if len(questions) >= desired_count:
            return questions[:desired_count]

    # Current topic (to keep exam tied to ongoing lesson).
    for game_type, activity_id in current_topic.daily_plan_for_level(current_level) + current_topic.extra_plan_for_level(current_level):
        card = _build_card_for_activity(
            game_type=game_type,
            language=language,
            level=current_level,
            activity_id=activity_id,
        )
        _append_from_card(card, current_topic.topic_key, current_topic.title, "current_topic")
        if len(questions) >= desired_count:
            return questions[:desired_count]

    # Closed-topic fallback from configured plans.
    for closed in closed_topics.values():
        topic_def = _topic_definition_for_key(language=language, topic_key=closed.topic_key)
        if topic_def is None:
            continue
        level = max(1, min(current_level, int(closed.closed_level)))
        plans = topic_def.daily_plan_for_level(level) + topic_def.extra_plan_for_level(level)
        for game_type, activity_id in plans:
            card = _build_card_for_activity(
                game_type=game_type,
                language=language,
                level=level,
                activity_id=activity_id,
            )
            _append_from_card(card, topic_def.topic_key, topic_def.title, "closed_fallback")
            if len(questions) >= desired_count:
                return questions[:desired_count]

    # Final fallback: pull additional items from the active level pool to reach target size.
    for game_type in registry.list_game_types():
        service = game_services.get(game_type)
        if service is None:
            continue
        for activity in service.get_activities(language=language, level=current_level):
            card = _build_card_for_activity(
                game_type=game_type,
                language=language,
                level=current_level,
                activity_id=activity.activity_id,
            )
            _append_from_card(card, current_topic.topic_key, current_topic.title, "pool_fallback")
            if len(questions) >= desired_count:
                return questions[:desired_count]

    return questions[:desired_count]


def _extra_game_cards_metadata(
    *,
    daily_game_types: list[str],
    language: str,
    level: int,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for game_type in registry.list_game_types():
        if game_type in daily_game_types:
            continue
        service = game_services.get(game_type)
        if service is None:
            continue
        # Only expose games that actually have activities for current language/level.
        if not service.get_activities(language=language, level=level):
            continue
        cards.append(
            {
                "game_type": game_type,
                "display_name": GAME_NAME_ALIASES.get(game_type, game_type),
                "language": language,
                "level": level,
                "deferred_load": True,
            }
        )
    return cards


@app.post("/api/games/daily")
async def get_daily_games(req: DailyGamesRequest) -> dict:
    logger.info(
        "daily_games learner_id=%s level_override_today=%s",
        req.learner_id,
        req.level_override_today,
    )
    state = memory.load_or_create(req.learner_id)
    prefs = memory.load_or_create_preferences(req.learner_id)
    preferred_language = prefs.preferred_language or "ja"
    secondary_translation_language = prefs.secondary_translation_language()
    if preferred_language not in AVAILABLE_LANGUAGES:
        preferred_language = "ja"
        memory.set_preferred_language(req.learner_id, preferred_language)

    snapshot = LearnerSnapshot(
        learner_id=state.learner_id,
        streak_days=state.streak_days,
        recent_accuracy=state.recent_accuracy,
        recent_games=[g for g in state.recent_games_csv.split(",") if g],
    )

    difficulty = planner.difficulty_for(snapshot)
    inferred_level = _service_level_from_difficulty(difficulty)
    stored_level = memory.level_for_language(req.learner_id, preferred_language, default_level=1)
    current_level = max(stored_level, inferred_level)
    if current_level != stored_level:
        memory.set_language_level(req.learner_id, preferred_language, current_level)

    requested_level = req.level_override_today
    today_level = current_level
    # Daily level override is disabled; users can review past topics instead.
    level_up_blocked = bool(requested_level is not None and int(requested_level) != int(current_level))

    topic, progress, today_iso = _daily_topic_for(learner_id=req.learner_id, language=preferred_language)
    progress = memory.set_daily_level_state(
        learner_id=req.learner_id,
        day_iso=today_iso,
        language=preferred_language,
        topic_key=topic.topic_key,
        level_state=today_level,
    )
    daily_plan = topic.daily_plan_for_level(today_level)
    daily_cards: list[dict[str, Any]] = []
    for game_type, activity_id in daily_plan:
        card = _build_card_for_activity(
            game_type=game_type,
            language=preferred_language,
            level=today_level,
            activity_id=activity_id,
            secondary_translation_language=secondary_translation_language,
        )
        if card is not None:
            daily_cards.append(card)

    daily_game_types = [card["game_type"] for card in daily_cards]
    daily_progress = _daily_progress_payload(progress=progress, daily_game_types=daily_game_types)
    daily_progress = _enrich_daily_progress_payload(
        learner_id=req.learner_id,
        language=preferred_language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=daily_progress,
    )
    extra_cards = _extra_game_cards_metadata(
        daily_game_types=daily_game_types,
        language=preferred_language,
        level=today_level,
    )

    available_cards = daily_cards + (extra_cards if daily_progress["extras_unlocked"] else [])

    selected_game: dict[str, Any] | None = None
    if daily_progress["lesson_completed"]:
        completed_games = set(daily_progress["completed_daily_games"])
        selected_game = next((card for card in daily_cards if card["game_type"] not in completed_games), None)
        if selected_game is None:
            available_games = [card["game_type"] for card in available_cards]
            selected = _choose_single_game(
                games=daily_game_types,
                available_games=available_games,
                learner_id=req.learner_id,
                language=preferred_language,
                today_level=today_level,
            )
            if selected is not None:
                selected_game = next((card for card in available_cards if card["game_type"] == selected), None)

    all_game_types = registry.list_game_types()
    all_daily_activities = registry.get_daily_activities(
        language=preferred_language,
        games=all_game_types,
        level=today_level,
    )
    all_cards: list[dict[str, Any]] = []
    for game in all_game_types:
        activity = all_daily_activities.get(game)
        if activity is None:
            continue
        card = _build_card_for_activity(
            game_type=game,
            language=preferred_language,
            level=today_level,
            activity_id=activity.activity_id,
            secondary_translation_language=secondary_translation_language,
        )
        if card is not None:
            all_cards.append(card)

    # When OpenAI is configured, enrich daily/reviewable cards with generated prompts.
    # Core game payload stays deterministic; only the instructional text becomes dynamic.
    ai_target_cards: list[dict[str, Any]] = [*daily_cards, *all_cards]
    await _attach_ai_prompts_to_cards(
        cards=ai_target_cards,
        difficulty=difficulty,
        learner_note=f"Topic={topic.title}; level={today_level}",
        secondary_translation_language=secondary_translation_language,
        context="daily_games",
    )
    ai_prompts_daily = sum(1 for card in daily_cards if str(card.get("ai_prompt_source") or "").lower() == "openai")
    ai_prompts_all = sum(1 for card in all_cards if str(card.get("ai_prompt_source") or "").lower() == "openai")

    response = _ui_state(
        learner_id=req.learner_id,
        preferred_language=preferred_language,
        difficulty=difficulty,
        today_level=today_level,
        overridden=False,
        secondary_translation_language=secondary_translation_language,
    )
    response["topic"] = {
        "topic_key": topic.topic_key,
        "title": topic.title,
        "description": topic.description,
    }
    response["lesson"] = _topic_lesson_payload(
        topic=topic,
        level=today_level,
        secondary_translation_language=secondary_translation_language,
    )
    response["daily_progress"] = daily_progress
    response["daily_games"] = daily_cards
    response["extra_games"] = extra_cards
    response["level_up_blocked"] = level_up_blocked
    response["selected_game"] = selected_game
    response["available_games"] = available_cards
    response["all_games"] = all_cards
    response["learning_contract"] = _learning_contract_payload(daily_required_games=len(daily_cards))
    logger.info(
        "daily_games_ready learner_id=%s language=%s topic=%s current_level=%s today_level=%s selected_game=%s daily=%s extras=%s available=%s all=%s ai_prompts_daily=%s ai_prompts_all=%s lesson_completed=%s level_up_blocked=%s level_override_requested=%s",
        req.learner_id,
        preferred_language,
        topic.topic_key,
        current_level,
        today_level,
        None if selected_game is None else selected_game["game_type"],
        len(daily_cards),
        len(extra_cards),
        len(available_cards),
        len(all_cards),
        ai_prompts_daily,
        ai_prompts_all,
        daily_progress["lesson_completed"],
        level_up_blocked,
        requested_level,
    )
    return _translate_response_for_learner(
        learner_id=req.learner_id,
        context="daily_games",
        payload=response,
    )


@app.post("/api/games/lesson/complete")
def complete_daily_lesson(req: DailyLessonCompleteRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("lesson_complete_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    topic, _progress, today_iso = _daily_topic_for(learner_id=learner_id, language=language)
    requested_topic = (req.topic_key or "").strip()
    if requested_topic and requested_topic != topic.topic_key:
        logger.warning(
            "lesson_complete_topic_mismatch learner_id=%s requested=%s expected=%s",
            learner_id,
            requested_topic,
            topic.topic_key,
        )
        return {"error": f"Topic mismatch for today: {requested_topic}"}

    progress = memory.mark_lesson_completed(
        learner_id=learner_id,
        day_iso=today_iso,
        language=language,
        topic_key=topic.topic_key,
    )
    current_level = memory.level_for_language(learner_id, language, default_level=1)
    level_state = int(progress.level_state or current_level)
    daily_game_types = [game_type for game_type, _activity_id in topic.daily_plan_for_level(level_state)]
    daily_progress = _daily_progress_payload(progress, daily_game_types=daily_game_types)
    daily_progress = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=daily_progress,
    )
    logger.info(
        "lesson_complete learner_id=%s language=%s topic=%s",
        learner_id,
        language,
        topic.topic_key,
    )
    return _translate_response_for_learner(
        learner_id=learner_id,
        context="lesson_complete",
        payload={
        "saved": True,
        "topic_key": topic.topic_key,
        "daily_progress": daily_progress,
        },
    )


@app.post("/api/games/extra/load")
async def load_extra_game(req: ExtraGameLoadRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    game_type = req.game_type.strip()
    secondary_translation_language = _secondary_translation_for_learner(learner_id)
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("extra_game_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    topic, progress, _today_iso = _daily_topic_for(learner_id=learner_id, language=language)
    requested_topic = (req.topic_key or "").strip()
    if requested_topic and requested_topic != topic.topic_key:
        logger.warning(
            "extra_game_topic_mismatch learner_id=%s requested=%s expected=%s",
            learner_id,
            requested_topic,
            topic.topic_key,
        )
        return {"error": f"Topic mismatch for today: {requested_topic}"}

    today_level = int(progress.level_state or memory.level_for_language(learner_id, language, default_level=1))
    daily_game_types = [game_type_key for game_type_key, _ in topic.daily_plan_for_level(today_level)]
    daily_progress = _daily_progress_payload(progress=progress, daily_game_types=daily_game_types)
    daily_progress = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=today_level,
        topic_key=topic.topic_key,
        today_iso=_today_iso,
        daily_progress=daily_progress,
    )
    if not daily_progress["extras_unlocked"]:
        logger.warning(
            "extra_game_locked learner_id=%s language=%s topic=%s game_type=%s",
            learner_id,
            language,
            topic.topic_key,
            game_type,
        )
        return {"error": "Extra games are locked. Complete lesson and daily games first."}

    available_extra_cards = _extra_game_cards_metadata(
        daily_game_types=daily_game_types,
        language=language,
        level=today_level,
    )
    allowed_extra_types = {card["game_type"] for card in available_extra_cards}
    if game_type not in allowed_extra_types:
        logger.warning(
            "extra_game_not_allowed learner_id=%s language=%s topic=%s game_type=%s",
            learner_id,
            language,
            topic.topic_key,
            game_type,
        )
        return {"error": f"Extra game not available: {game_type}"}

    card, selection_source = _select_extra_card_for_game_type(
        learner_id=learner_id,
        language=language,
        today_topic=topic,
        today_level=today_level,
        game_type=game_type,
        today_iso=_today_iso,
        secondary_translation_language=secondary_translation_language,
    )

    if card is None:
        logger.warning(
            "extra_game_card_missing learner_id=%s language=%s topic=%s game_type=%s level=%s",
            learner_id,
            language,
            topic.topic_key,
            game_type,
            today_level,
        )
        return {"error": f"No activity available for extra game: {game_type}"}

    card_topic_key = str(card.get("topic_key", topic.topic_key))
    card_topic_title = _topic_title(language=language, topic_key=card_topic_key)
    try:
        ai_prompt_result = await openai_planner.generate_extra_game_prompt(
            language=language,
            topic_title=card_topic_title,
            game_type=game_type,
            level=today_level,
        )
    except Exception:
        logger.exception(
            "extra_game_ai_prompt_failed learner_id=%s language=%s topic=%s game_type=%s level=%s",
            learner_id,
            language,
            topic.topic_key,
            game_type,
            today_level,
        )
        ai_prompt_result = {
            "source": "fallback",
            "text": f"Topic: {card_topic_title}. Try this {game_type} activity at level {today_level}.",
        }
    ai_prompt = str(ai_prompt_result.get("text", "")).strip()
    if ai_prompt:
        card["prompt"] = f"{ai_prompt}\n\n{card.get('prompt', '')}".strip()
    card["ai_generated_prompt"] = ai_prompt
    card["ai_prompt_source"] = ai_prompt_result.get("source", "fallback")
    logger.info(
        "extra_game_loaded learner_id=%s language=%s topic=%s game_type=%s level=%s ai_source=%s selection_source=%s card_topic=%s",
        learner_id,
        language,
        topic.topic_key,
        game_type,
        today_level,
        card["ai_prompt_source"],
        selection_source,
        card_topic_key,
    )
    return _translate_response_for_learner(
        learner_id=learner_id,
        context="extra_game_load",
        payload={
        "card": card,
        "daily_progress": daily_progress,
        },
    )


@app.post("/api/topics/closed")
def list_closed_topics(req: ClosedTopicsRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("closed_topics_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    closed = memory.list_closed_topics(learner_id=learner_id, language=language)
    topics = [
        {
            "topic_key": item.topic_key,
            "topic_title": _topic_title(language=language, topic_key=item.topic_key),
            "closed_day_iso": item.closed_day_iso,
            "closed_level": int(item.closed_level),
            "reason": item.reason,
        }
        for item in closed
    ]
    logger.info(
        "closed_topics_listed learner_id=%s language=%s count=%s",
        learner_id,
        language,
        len(topics),
    )
    return {
        "learner_id": learner_id,
        "language": language,
        "closed_topics": topics,
        "closed_topics_count": len(topics),
    }


@app.post("/api/topics/review")
async def load_topic_review(req: TopicReviewRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    secondary_translation_language = _secondary_translation_for_learner(learner_id)
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("topic_review_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    topic = _topic_definition_for_key(language=language, topic_key=req.topic_key)
    if topic is None:
        logger.warning(
            "topic_review_not_found learner_id=%s language=%s topic_key=%s",
            learner_id,
            language,
            req.topic_key,
        )
        return {"error": f"Unknown topic: {req.topic_key}"}

    # Review mode is restricted to topics that were already closed/learned.
    closed_topic_keys = {
        item.topic_key
        for item in memory.list_closed_topics(learner_id=learner_id, language=language)
    }
    logger.info(
        "topic_review_gate learner_id=%s language=%s requested_topic=%s closed_topics_count=%s",
        learner_id,
        language,
        topic.topic_key,
        len(closed_topic_keys),
    )
    if topic.topic_key not in closed_topic_keys:
        logger.warning(
            "topic_review_not_closed learner_id=%s language=%s topic_key=%s closed_topics_count=%s",
            learner_id,
            language,
            topic.topic_key,
            len(closed_topic_keys),
        )
        return {"error": f"Topic is not closed yet: {topic.topic_key}"}

    current_level = memory.level_for_language(learner_id=learner_id, language=language, default_level=1)
    plans = topic.daily_plan_for_level(current_level) + topic.extra_plan_for_level(current_level)
    seen_game_types: set[str] = set()
    review_cards: list[dict[str, Any]] = []
    for game_type, activity_id in plans:
        if game_type in seen_game_types:
            continue
        card = _build_card_for_activity(
            game_type=game_type,
            language=language,
            level=current_level,
            activity_id=activity_id,
            secondary_translation_language=secondary_translation_language,
        )
        if card is None:
            continue
        seen_game_types.add(game_type)
        review_cards.append(card)

    # Keep review prompts aligned with current proficiency while using the same IA generator.
    level_hint = 3 if current_level <= 1 else (6 if current_level == 2 else 9)
    await _attach_ai_prompts_to_cards(
        cards=review_cards,
        difficulty=level_hint,
        learner_note=f"Topic={topic.title}; review_mode=true; level={current_level}",
        secondary_translation_language=secondary_translation_language,
        context="topic_review",
    )
    ai_prompts_review = sum(1 for card in review_cards if str(card.get("ai_prompt_source") or "").lower() == "openai")

    logger.info(
        "topic_review_loaded learner_id=%s language=%s topic=%s level=%s games=%s ai_prompts_review=%s",
        learner_id,
        language,
        topic.topic_key,
        current_level,
        len(review_cards),
        ai_prompts_review,
    )
    return _translate_response_for_learner(
        learner_id=learner_id,
        context="topic_review",
        payload={
        "learner_id": learner_id,
        "language": language,
        "topic": {
            "topic_key": topic.topic_key,
            "title": topic.title,
            "description": topic.description,
        },
        "lesson": _topic_lesson_payload(
            topic=topic,
            level=current_level,
            secondary_translation_language=secondary_translation_language,
        ),
        "review_mode": True,
        "review_games": review_cards,
        "selected_game": review_cards[0] if review_cards else None,
        },
    )


@app.post("/api/exams/weekly")
def take_weekly_exam(req: WeeklyExamRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    requested_mode = (req.mode or "").strip().lower()
    weekly_force_legacy = WEEKLY_EXAM_FORCE_LEGACY
    if requested_mode in {"legacy", "cumulative"}:
        weekly_force_legacy = requested_mode != "cumulative"
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("weekly_exam_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    topic, progress, today_iso = _daily_topic_for(learner_id=learner_id, language=language)
    requested_topic = (req.topic_key or "").strip()
    if requested_topic and requested_topic != topic.topic_key:
        logger.warning(
            "weekly_exam_topic_mismatch learner_id=%s requested=%s expected=%s",
            learner_id,
            requested_topic,
            topic.topic_key,
        )
        return {"error": f"Topic mismatch for today: {requested_topic}"}

    current_level = memory.level_for_language(learner_id=learner_id, language=language, default_level=1)
    daily_game_types = [game for game, _activity_id in topic.daily_plan_for_level(int(progress.level_state or current_level))]
    base_daily = _daily_progress_payload(progress=progress, daily_game_types=daily_game_types)
    insights = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=base_daily,
    )
    if not insights.get("weekly_exam_due"):
        logger.info("weekly_exam_not_due learner_id=%s language=%s topic=%s", learner_id, language, topic.topic_key)
        return _translate_response_for_learner(
            learner_id=learner_id,
            context="weekly_exam.not_due",
            payload={
            "error": "Weekly mini-exam is not due yet.",
            "daily_progress": insights,
            },
        )

    questions = _weekly_exam_questions(
        learner_id=learner_id,
        language=language,
        current_topic=topic,
        current_level=current_level,
        today_iso=today_iso,
        question_count=req.question_count,
    )
    if not questions:
        logger.warning(
            "weekly_exam_questions_empty learner_id=%s language=%s topic=%s",
            learner_id,
            language,
            topic.topic_key,
        )
        return _translate_response_for_learner(
            learner_id=learner_id,
            context="weekly_exam.questions_empty",
            payload={
            "error": "No weekly exam questions available yet.",
            "daily_progress": insights,
            },
        )

    # Two-step weekly exam:
    # 1) Call without answers -> receive cumulative questions.
    # 2) Submit answers -> receive score/pass result.
    submitted_answers = list(req.answers or [])
    if weekly_force_legacy:
        if submitted_answers:
            logger.info(
                "weekly_exam_legacy_answers_ignored learner_id=%s language=%s topic=%s answers=%s",
                learner_id,
                language,
                topic.topic_key,
                len(submitted_answers),
            )
        lesson_and_daily_done = bool(progress.lesson_completed) and len(base_daily["completed_daily_games"]) >= len(daily_game_types)
        target_score = int(insights["topic_day_target_score"])
        exam_score = int(req.exam_score) if req.exam_score is not None else int(base_daily["daily_score"])
        failure_total = sum(int(value) for value in dict(insights.get("topic_failure_totals", {})).values())
        min_pass_score = max(120, int(round(target_score * 0.85)))
        passed = bool(lesson_and_daily_done and exam_score >= min_pass_score and failure_total <= 16)
        memory.save_weekly_exam_result(learner_id=learner_id, day_iso=today_iso, passed=passed)
        refreshed_daily = _enrich_daily_progress_payload(
            learner_id=learner_id,
            language=language,
            current_level=current_level,
            topic_key=topic.topic_key,
            today_iso=today_iso,
            daily_progress=base_daily,
        )
        logger.info(
            "weekly_exam_generated_legacy learner_id=%s language=%s topic=%s questions=%s passed=%s exam_score=%s min_pass=%s",
            learner_id,
            language,
            topic.topic_key,
            len(questions),
            passed,
            exam_score,
            min_pass_score,
        )
        return _translate_response_for_learner(
            learner_id=learner_id,
            context="weekly_exam.legacy",
            payload={
            "requires_answers": False,
            "legacy_mode": True,
            "passed": passed,
            "exam_score": exam_score,
            "min_pass_score": min_pass_score,
            "question_count": len(questions),
            "questions_preview": questions,
            "feedback": (
                "Weekly mini-exam passed in legacy mode."
                if passed
                else "Weekly mini-exam failed. Complete daily games and improve consistency before retrying next week."
            ),
            "daily_progress": refreshed_daily,
            },
        )

    # Cumulative mode phase 1: return generated questions so the client can submit answers in a second call.
    if not submitted_answers:
        logger.info(
            "weekly_exam_questions_generated_cumulative learner_id=%s language=%s topic=%s questions=%s",
            learner_id,
            language,
            topic.topic_key,
            len(questions),
        )
        return _translate_response_for_learner(
            learner_id=learner_id,
            context="weekly_exam.phase_one",
            payload={
            "requires_answers": True,
            "legacy_mode": False,
            "question_count": len(questions),
            "questions": questions,
            "daily_progress": insights,
            },
        )

    question_by_id = {str(question["question_id"]): question for question in questions}
    question_by_key = {
        (
            str(question["topic_key"]),
            str(question["game_type"]),
            str(question["item_id"]),
        ): question
        for question in questions
    }
    answer_results: list[dict[str, Any]] = []
    raw_scores: list[int] = []
    for answer in submitted_answers:
        if not isinstance(answer, dict):
            answer_results.append({"error": "Invalid answer format."})
            raw_scores.append(0)
            continue

        answer_question = None
        answer_question_id = str(answer.get("question_id", "")).strip()
        if answer_question_id and answer_question_id in question_by_id:
            answer_question = question_by_id[answer_question_id]
        else:
            answer_key = (
                str(answer.get("topic_key", "")).strip(),
                str(answer.get("game_type", "")).strip(),
                str(answer.get("item_id", "")).strip(),
            )
            answer_question = question_by_key.get(answer_key)
        if answer_question is None:
            answer_results.append(
                {
                    "question_id": answer_question_id or None,
                    "error": "Answer does not match any generated weekly exam question.",
                    "score": 0,
                }
            )
            raw_scores.append(0)
            continue

        game_type = str(answer_question["game_type"])
        item_id = str(answer_question["item_id"])
        answer_payload = dict(answer.get("payload") or {})
        answer_payload.setdefault("item_id", item_id)
        answer_payload.setdefault("topic_key", str(answer_question["topic_key"]))
        level = int(answer_question.get("level", current_level) or current_level)

        try:
            result = _evaluate_game_payload(
                game_type=game_type,
                language=language,
                level=level,
                retry_count=0,
                payload=answer_payload,
            )
        except ValueError as exc:
            result = {"error": str(exc)}
        except Exception:
            logger.exception("weekly_exam_answer_unhandled learner_id=%s game_type=%s item_id=%s", learner_id, game_type, item_id)
            result = {"error": "Internal error while evaluating weekly answer"}

        question_score = 0
        if isinstance(result, dict) and "score" in result:
            try:
                question_score = max(0, min(100, int(result.get("score", 0))))
            except (TypeError, ValueError):
                question_score = 0
        raw_scores.append(question_score)

        _update_item_review_state(
            learner_id=learner_id,
            language=language,
            game_type=game_type,
            item_id=item_id,
            payload=answer_payload,
            score=question_score,
        )
        answer_results.append(
            {
                "question_id": answer_question["question_id"],
                "topic_key": answer_question["topic_key"],
                "game_type": game_type,
                "item_id": item_id,
                "score": question_score,
                "result": result,
            }
        )

    score_count = max(1, len(raw_scores))
    raw_average = sum(raw_scores) / score_count
    exam_score = int(round((raw_average / 100.0) * 300.0))

    lesson_and_daily_done = bool(progress.lesson_completed) and len(base_daily["completed_daily_games"]) >= len(daily_game_types)
    target_score = int(insights["topic_day_target_score"])
    failure_total = sum(int(value) for value in dict(insights.get("topic_failure_totals", {})).values())
    min_pass_score = max(120, int(round(target_score * 0.85)))
    answered_enough = len(answer_results) >= max(3, min(len(questions), 6))
    passed = bool(lesson_and_daily_done and answered_enough and exam_score >= min_pass_score and failure_total <= 16)

    memory.save_weekly_exam_result(learner_id=learner_id, day_iso=today_iso, passed=passed)
    refreshed_daily = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=base_daily,
    )
    logger.info(
        "weekly_exam_done learner_id=%s language=%s topic=%s passed=%s exam_score=%s min_pass=%s questions=%s answered=%s",
        learner_id,
        language,
        topic.topic_key,
        passed,
        exam_score,
        min_pass_score,
        len(questions),
        len(answer_results),
    )
    return _translate_response_for_learner(
        learner_id=learner_id,
        context="weekly_exam.phase_two",
        payload={
        "requires_answers": False,
        "passed": passed,
        "exam_score": exam_score,
        "min_pass_score": min_pass_score,
        "question_count": len(questions),
        "answers_evaluated": len(answer_results),
        "answer_results": answer_results,
        "feedback": (
            "Weekly mini-exam passed. You can keep building toward the level exam."
            if passed
            else "Weekly mini-exam failed. Complete daily games and improve consistency before retrying next week."
        ),
        "daily_progress": refreshed_daily,
        },
    )


@app.post("/api/exams/level")
def take_level_exam(req: LevelExamRequest) -> dict:
    learner_id = req.learner_id or DEFAULT_LEARNER_ID
    language = (req.language or "ja").strip().lower()
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("level_exam_invalid_language learner_id=%s language=%s", learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    topic, progress, today_iso = _daily_topic_for(learner_id=learner_id, language=language)
    current_level = memory.level_for_language(learner_id=learner_id, language=language, default_level=1)
    target_level = int(req.target_level or (current_level + 1))
    if target_level <= current_level:
        return {"error": f"Target level must be above current level ({current_level})."}
    if target_level > 3:
        return {"error": "Target level is not supported."}

    already_passed = memory.level_exam_passed(
        learner_id=learner_id,
        language=language,
        from_level=current_level,
        to_level=target_level,
    )
    if already_passed:
        return {"error": "This level transition has already been passed."}

    daily_game_types = [game for game, _activity_id in topic.daily_plan_for_level(int(progress.level_state or current_level))]
    base_daily = _daily_progress_payload(progress=progress, daily_game_types=daily_game_types)
    insights = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=base_daily,
    )
    ready_flag = "ready_to_level_2" if target_level == 2 else "ready_to_level_3"
    if not bool(insights.get(ready_flag)):
        logger.info(
            "level_exam_not_ready learner_id=%s language=%s current_level=%s target_level=%s",
            learner_id,
            language,
            current_level,
            target_level,
        )
        return {
            "error": "Level exam is not unlocked yet.",
            "target_level": target_level,
            "daily_progress": insights,
        }

    exam_score = int(req.exam_score) if req.exam_score is not None else int(base_daily["daily_score"])
    target_score = int(insights["topic_day_target_score"])
    pass_threshold = min(300, max(170 if target_level == 2 else 210, int(round(target_score * 0.95))))
    failure_total = sum(int(value) for value in dict(insights.get("topic_failure_totals", {})).values())
    retention = insights.get("retention_ratio_percent")
    retention_ok = retention is None if target_level == 2 else retention is not None
    if target_level == 2 and retention is not None:
        retention_ok = retention >= 70.0
    if target_level == 3 and retention is not None:
        retention_ok = retention >= 80.0

    failure_limit = 12 if target_level == 2 else 8
    passed = bool(exam_score >= pass_threshold and failure_total <= failure_limit and retention_ok)
    promoted = False
    if passed:
        memory.mark_level_exam_passed(
            learner_id=learner_id,
            language=language,
            from_level=current_level,
            to_level=target_level,
        )
        memory.set_language_level(learner_id=learner_id, language=language, level=target_level)
        memory.mark_topic_closed(
            learner_id=learner_id,
            language=language,
            topic_key=topic.topic_key,
            closed_day_iso=today_iso,
            closed_level=target_level,
            reason=f"level_exam_{current_level}_to_{target_level}",
        )
        promoted = True

    refreshed_level = memory.level_for_language(learner_id=learner_id, language=language, default_level=1)
    refreshed_progress = memory.load_or_create_daily_topic_progress(
        learner_id=learner_id,
        day_iso=today_iso,
        language=language,
        topic_key=topic.topic_key,
    )
    if promoted:
        # Keep level state aligned with the newly promoted level in this response.
        refreshed_progress = memory.set_daily_level_state(
            learner_id=learner_id,
            day_iso=today_iso,
            language=language,
            topic_key=topic.topic_key,
            level_state=refreshed_level,
        )
    refreshed_daily_game_types = [
        game for game, _activity_id in topic.daily_plan_for_level(int(refreshed_progress.level_state or refreshed_level))
    ]
    refreshed_base_daily = _daily_progress_payload(progress=refreshed_progress, daily_game_types=refreshed_daily_game_types)
    refreshed_daily = _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=refreshed_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=refreshed_base_daily,
    )
    logger.info(
        "level_exam_refresh learner_id=%s language=%s promoted=%s refreshed_level=%s refreshed_level_state=%s refreshed_daily_score=%s",
        learner_id,
        language,
        promoted,
        refreshed_level,
        int(refreshed_progress.level_state),
        int(refreshed_progress.daily_score),
    )
    logger.info(
        "level_exam_done learner_id=%s language=%s current_level=%s target_level=%s passed=%s exam_score=%s threshold=%s",
        learner_id,
        language,
        current_level,
        target_level,
        passed,
        exam_score,
        pass_threshold,
    )
    return _translate_response_for_learner(
        learner_id=learner_id,
        context="level_exam",
        payload={
        "passed": passed,
        "promoted": promoted,
        "current_level": refreshed_level,
        "target_level": target_level,
        "exam_score": exam_score,
        "pass_threshold": pass_threshold,
        "feedback": (
            f"Level exam passed. Promoted to level {target_level}."
            if passed
            else "Level exam failed. Keep training and retry when metrics improve."
        ),
        "daily_progress": refreshed_daily,
        },
    )


@app.post("/api/ui/language")
def update_ui_language(req: LanguageUpdateRequest) -> dict:
    language = req.language.strip().lower()
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("ui_language_invalid learner_id=%s requested=%s", req.learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    memory.load_or_create(req.learner_id)
    prefs = memory.load_or_create_preferences(req.learner_id)
    levels = prefs.levels()
    secondary_translation_language = prefs.secondary_translation_language()
    if language not in levels:
        memory.set_language_level(req.learner_id, language, 1)

    memory.set_preferred_language(req.learner_id, language)

    state = memory.load_or_create(req.learner_id)
    snapshot = LearnerSnapshot(
        learner_id=state.learner_id,
        streak_days=state.streak_days,
        recent_accuracy=state.recent_accuracy,
        recent_games=[g for g in state.recent_games_csv.split(",") if g],
    )
    difficulty = planner.difficulty_for(snapshot)
    current_level = memory.level_for_language(req.learner_id, language, default_level=1)
    logger.info(
        "ui_language_updated learner_id=%s language=%s current_level=%s difficulty=%s",
        req.learner_id,
        language,
        current_level,
        difficulty,
    )
    return _ui_state(
        learner_id=req.learner_id,
        preferred_language=language,
        difficulty=difficulty,
        today_level=current_level,
        overridden=False,
        secondary_translation_language=secondary_translation_language,
    )


@app.post("/api/ui/secondary-translation")
def update_ui_secondary_translation(req: SecondaryTranslationUpdateRequest) -> dict:
    requested = _normalize_secondary_language(req.secondary_language)
    raw = (req.secondary_language or "").strip().lower()
    if raw and raw not in {"off", "none", "null"} and requested is None:
        logger.warning(
            "ui_secondary_translation_invalid learner_id=%s requested=%s",
            req.learner_id,
            raw,
        )
        return {"error": f"Unsupported secondary translation language: {raw}"}

    memory.load_or_create(req.learner_id)
    prefs = memory.load_or_create_preferences(req.learner_id)
    preferred_language = (prefs.preferred_language or "ja").strip().lower()
    if preferred_language not in AVAILABLE_LANGUAGES:
        preferred_language = "ja"
        memory.set_preferred_language(req.learner_id, preferred_language)
    memory.set_secondary_translation_language(req.learner_id, requested)

    state = memory.load_or_create(req.learner_id)
    snapshot = LearnerSnapshot(
        learner_id=state.learner_id,
        streak_days=state.streak_days,
        recent_accuracy=state.recent_accuracy,
        recent_games=[g for g in state.recent_games_csv.split(",") if g],
    )
    difficulty = planner.difficulty_for(snapshot)
    current_level = memory.level_for_language(req.learner_id, preferred_language, default_level=1)
    logger.info(
        "ui_secondary_translation_updated learner_id=%s secondary_language=%s",
        req.learner_id,
        requested or "off",
    )
    return _ui_state(
        learner_id=req.learner_id,
        preferred_language=preferred_language,
        difficulty=difficulty,
        today_level=current_level,
        overridden=False,
        secondary_translation_language=requested,
    )


@app.post("/api/session/complete")
def save_session(req: SessionResult) -> dict:
    logger.info(
        "session_complete learner_id=%s accuracy=%.3f streak_days=%s games_done=%s",
        req.learner_id,
        req.accuracy,
        req.streak_days,
        len(req.games_done),
    )
    memory.save_session(
        learner_id=req.learner_id,
        streak_days=req.streak_days,
        recent_accuracy=req.accuracy,
        recent_games=req.games_done,
    )
    return {"saved": True}


@app.post("/api/pronunciation/evaluate")
async def evaluate_pronunciation(req: PronunciationRequest) -> dict:
    logger.info(
        "pronunciation_eval expected_len=%s transcript_len=%s",
        len(req.expected or ""),
        len(req.transcript or ""),
    )
    return await elevenlabs.evaluate_pronunciation(req.transcript, req.expected)


@app.post("/api/audio/tts")
async def generate_tts_audio(req: TextToSpeechRequest) -> dict:
    language = req.language.strip().lower()
    text = req.text.strip()
    warning_message = ""
    if req.play_count > 3:
        warning_message = "Warning: repeated TTS playback may increase token usage."
        logger.warning(
            "tts_replay_warning language=%s play_count=%s text_len=%s",
            language,
            req.play_count,
            len(text),
        )
    if language != "ja":
        logger.warning("tts_unsupported_language language=%s", language)
        response = {"error": f"Unsupported language for TTS: {language}"}
        if warning_message:
            response["warning"] = warning_message
        return response

    if not text:
        response = {"error": "Empty text for TTS"}
        if warning_message:
            response["warning"] = warning_message
        return response

    logger.info("tts_request language=%s text_len=%s", language, len(text))
    audio_bytes = await elevenlabs.tts_japanese(text)
    if not audio_bytes:
        logger.warning("tts_unavailable reason=missing_credentials_or_provider text_len=%s", len(text))
        response = {"error": "TTS unavailable. Check ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID."}
        if warning_message:
            response["warning"] = warning_message
        return response

    encoded = base64.b64encode(audio_bytes).decode("ascii")
    response = {
        "mime_type": "audio/mpeg",
        "audio_data_url": f"data:audio/mpeg;base64,{encoded}",
    }
    if warning_message:
        response["warning"] = warning_message
    return response


@app.post("/api/audio/stt")
async def transcribe_audio(
    language: str = Form("ja"),
    audio_file: UploadFile = File(...),
) -> dict:
    normalized_language = language.strip().lower()
    if normalized_language != "ja":
        logger.warning("stt_unsupported_language language=%s", normalized_language)
        return {"error": f"Unsupported language for STT: {normalized_language}"}

    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return {"error": "No audio received for transcription."}

    mime_type = audio_file.content_type or "application/octet-stream"
    filename = audio_file.filename or "audio.webm"
    logger.info(
        "stt_request language=%s filename=%s content_type=%s size_bytes=%s",
        normalized_language,
        filename,
        mime_type,
        len(audio_bytes),
    )

    result = await openai_planner.transcribe_audio(
        audio_bytes=audio_bytes,
        filename=filename,
        mime_type=mime_type,
        language=normalized_language,
    )
    transcript = (result.get("transcript") or "").strip()
    if not transcript:
        logger.warning("stt_failed language=%s detail=%s", normalized_language, result.get("error", "no_detail"))
        return {
            "error": result.get("error", "Audio transcription failed."),
            "details": result.get("details", []),
        }

    logger.info("stt_done language=%s transcript_len=%s model=%s", normalized_language, len(transcript), result.get("model"))
    return {
        "transcript": transcript,
        "model": result.get("model", ""),
    }


def _mark_daily_game_progress(
    learner_id: str,
    language: str,
    level: int,
    game_type: str,
    item_id: str,
    score: int | None = None,
    register_failure: bool = False,
) -> dict[str, Any] | None:
    if language not in AVAILABLE_LANGUAGES:
        return None

    topic, _progress, today_iso = _daily_topic_for(learner_id=learner_id, language=language)
    daily_plan = dict(topic.daily_plan_for_level(level))
    expected_item_id = daily_plan.get(game_type)
    if expected_item_id is None or expected_item_id != item_id:
        return None

    progress = memory.mark_daily_game_completed(
        learner_id=learner_id,
        day_iso=today_iso,
        language=language,
        topic_key=topic.topic_key,
        game_type=game_type,
    )
    if register_failure:
        progress = memory.increment_daily_game_failure(
            learner_id=learner_id,
            day_iso=today_iso,
            language=language,
            topic_key=topic.topic_key,
            game_type=game_type,
            increment=1,
        )
    daily_game_types = list(daily_plan.keys())
    if score is not None:
        progress = memory.upsert_daily_game_score(
            learner_id=learner_id,
            day_iso=today_iso,
            language=language,
            topic_key=topic.topic_key,
            game_type=game_type,
            score=score,
            allowed_daily_games=daily_game_types,
            max_total_score=300,
        )
    payload = _daily_progress_payload(progress=progress, daily_game_types=daily_game_types)
    current_level = memory.level_for_language(learner_id, language, default_level=1)
    return _enrich_daily_progress_payload(
        learner_id=learner_id,
        language=language,
        current_level=current_level,
        topic_key=topic.topic_key,
        today_iso=today_iso,
        daily_progress=payload,
    )


def _evaluate_game_payload(
    *,
    game_type: str,
    language: str,
    level: int,
    retry_count: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    service = game_services.get(game_type)
    if service is None:
        return {"error": f"Unsupported game: {game_type}"}

    if game_type == GAME_TYPE_GRAMMAR_PARTICLE_FIX:
        return service.evaluate_attempt(
            GrammarParticleAttempt(
                language=language,
                item_id=payload.get("item_id", ""),
                selected_particle=payload.get("selected_particle", ""),
                level=level,
            )
        )
    if game_type == GAME_TYPE_SENTENCE_ORDER:
        result = service.evaluate_attempt(
            SentenceOrderAttempt(
                language=language,
                item_id=payload.get("item_id", ""),
                ordered_tokens_by_user=payload.get("ordered_tokens_by_user", []),
                level=level,
            )
        )
        placement_penalty = max(0, min(100, int(payload.get("sentence_order_penalty", 0) or 0)))
        base_score = int(result.get("score", 0))
        result["sentence_order_penalty"] = placement_penalty
        result["score"] = max(0, base_score - placement_penalty)
        return result
    if game_type == GAME_TYPE_LISTENING_GAP_FILL:
        return service.evaluate_attempt(
            ListeningGapFillAttempt(
                language=language,
                item_id=payload.get("item_id", ""),
                user_gap_tokens=payload.get("user_gap_tokens", []),
                level=level,
            )
        )
    if game_type == GAME_TYPE_MORA_ROMANIZATION:
        return service.evaluate_attempt(
            MoraRomanizationAttempt(
                language=language,
                item_id=payload.get("item_id", ""),
                user_romanized_text=payload.get("user_romanized_text", ""),
                level=level,
            )
        )
    if game_type == GAME_TYPE_CONTEXT_QUIZ:
        return service.evaluate_attempt(
            ContextQuizAttempt(
                language=language,
                item_id=payload.get("item_id", ""),
                selected_option_id=payload.get("selected_option_id", ""),
                level=level,
            )
        )
    if game_type == GAME_TYPE_KANJI_MATCH:
        pairs = service.get_pairs(language=language, level=level)
        return service.evaluate_attempt(
            KanjiMatchAttempt(
                language=language,
                expected_pairs=pairs,
                learner_readings=payload.get("learner_readings", {}),
                learner_meanings=payload.get("learner_meanings", payload.get("learner_matches", {})),
                learner_matches=payload.get("learner_matches", {}),
                level=level,
            )
        )
    if game_type == ALIAS_GAME_TYPE_KANA_SPEED_ROUND:
        return service.evaluate_attempt(
            ScriptSpeedAttempt(
                language=language,
                sequence_expected=payload.get("sequence_expected", []),
                sequence_read=payload.get("sequence_read", []),
                elapsed_seconds=float(payload.get("elapsed_seconds", 1.0)),
                level=level,
                expected_text=payload.get("expected_text", ""),
                recognized_text=payload.get("recognized_text", ""),
                audio_duration_seconds=float(payload.get("audio_duration_seconds", payload.get("elapsed_seconds", 1.0))),
                speech_seconds=float(payload.get("speech_seconds", payload.get("elapsed_seconds", 1.0))),
                pause_seconds=float(payload.get("pause_seconds", 0.2)),
                pitch_track_hz=payload.get("pitch_track_hz", [150.0, 149.0, 151.0]),
                retry_count=retry_count,
            )
        )
    if game_type == GAME_TYPE_PRONUNCIATION_MATCH:
        return service.evaluate_attempt(
            PronunciationMatchAttempt(
                language=language,
                expected_text=payload.get("expected_text", ""),
                recognized_text=payload.get("recognized_text", ""),
                audio_duration_seconds=float(payload.get("audio_duration_seconds", 2.0)),
                speech_seconds=float(payload.get("speech_seconds", 1.8)),
                pause_seconds=float(payload.get("pause_seconds", 0.2)),
                pitch_track_hz=payload.get("pitch_track_hz", [150.0, 151.0, 149.0]),
                item_id=payload.get("item_id", ""),
                level=level,
                retry_count=retry_count,
            )
        )
    return {"error": f"Evaluation not implemented for: {game_type}"}


@app.post("/api/games/evaluate")
def evaluate_game(req: GameEvaluateRequest) -> dict:
    logger.info(
        "game_eval_start learner_id=%s game_type=%s language=%s level=%s retry_count=%s payload_keys=%s",
        req.learner_id,
        req.game_type,
        req.language,
        req.level,
        req.retry_count,
        ",".join(sorted(req.payload.keys())),
    )
    try:
        result = _evaluate_game_payload(
            game_type=req.game_type,
            language=req.language,
            level=req.level,
            retry_count=req.retry_count,
            payload=req.payload,
        )
    except ValueError as exc:
        logger.warning("game_eval_invalid game_type=%s detail=%s", req.game_type, str(exc))
        return {"error": str(exc)}
    except Exception:
        logger.exception("game_eval_unhandled game_type=%s", req.game_type)
        return {"error": "Internal error while evaluating game"}

    if isinstance(result, dict) and "error" in result:
        logger.warning("game_eval_error game_type=%s detail=%s", req.game_type, result["error"])
    else:
        item_id = str(req.payload.get("item_id", "")).strip()
        result_score = None
        if isinstance(result, dict) and "score" in result:
            try:
                result_score = int(result.get("score"))
            except (TypeError, ValueError):
                result_score = None

        if item_id and result_score is not None and not req.review_mode:
            _update_item_review_state(
                learner_id=req.learner_id,
                language=req.language,
                game_type=req.game_type,
                item_id=item_id,
                payload=req.payload,
                score=result_score,
            )

        if item_id and not req.review_mode:
            result_success = _is_success_result(result) if isinstance(result, dict) else None
            daily_progress = _mark_daily_game_progress(
                learner_id=req.learner_id,
                language=req.language,
                level=req.level,
                game_type=req.game_type,
                item_id=item_id,
                score=result_score,
                register_failure=(result_success is False),
            )
            if daily_progress is not None and isinstance(result, dict):
                result["daily_progress"] = daily_progress
        elif item_id and req.review_mode:
            logger.info(
                "game_eval_review_mode learner_id=%s game_type=%s item_id=%s",
                req.learner_id,
                req.game_type,
                item_id,
            )
        score = result.get("score") if isinstance(result, dict) else None
        logger.info("game_eval_done game_type=%s score=%s", req.game_type, score)
    if isinstance(result, dict):
        return _translate_response_for_learner(
            learner_id=req.learner_id,
            context=f"game_evaluate.{req.game_type}",
            payload=result,
        )
    return result
