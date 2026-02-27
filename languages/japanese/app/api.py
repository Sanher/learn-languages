from __future__ import annotations

import base64
import logging
import os
from datetime import date
from pathlib import Path
from random import Random
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
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
from .memory import ProgressMemory
from .services.elevenlabs_client import ElevenLabsService
from .services.openai_client import OpenAIPlanner
from .topic_flow import TopicDefinition, topic_for_day

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
ADDON_LANGUAGE_DATA_DIR = Path("/data") / "japanese"
LOCAL_LANGUAGE_DATA_DIR = BASE_DIR / "data" / "japanese"
DB_PATH = str((ADDON_LANGUAGE_DATA_DIR if Path("/data").exists() else LOCAL_LANGUAGE_DATA_DIR) / "progress.db")
DEFAULT_LEARNER_ID = os.getenv("HA_DEFAULT_LEARNER_ID", "ha_default_user")
AVAILABLE_LANGUAGES = ["ja"]
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
    "provider_config openai_key=%s openai_model=%s elevenlabs_key=%s elevenlabs_voice_id=%s elevenlabs_model_id=%s",
    bool(openai_planner.api_key),
    openai_planner.model,
    bool(elevenlabs.api_key),
    bool(elevenlabs.voice_id),
    elevenlabs.model_id,
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


class LanguageUpdateRequest(BaseModel):
    learner_id: str = DEFAULT_LEARNER_ID
    language: str


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/web/")
def web_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/web/{path:path}")
def web_assets(path: str) -> FileResponse:
    return FileResponse(WEB_DIR / path)


@app.get("/")
def root_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/app.js")
def root_app_js() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js")


@app.get("/styles.css")
def root_styles_css() -> FileResponse:
    return FileResponse(WEB_DIR / "styles.css")


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


def _ui_state(learner_id: str, preferred_language: str, difficulty: int, today_level: int, overridden: bool) -> dict[str, Any]:
    current_level = memory.level_for_language(learner_id, preferred_language, default_level=1)
    return {
        "learner_id": learner_id,
        "language": preferred_language,
        "available_languages": AVAILABLE_LANGUAGES,
        "difficulty": difficulty,
        "current_level": current_level,
        "today_level": today_level,
        "today_level_overridden": overridden,
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
    return {
        "topic_key": progress.topic_key,
        "lesson_completed": bool(progress.lesson_completed),
        "completed_daily_games": completed,
        "daily_games_required": daily_game_types,
        "daily_games_completed_count": len(completed),
        "daily_games_total": total_required,
        "extras_unlocked": extras_unlocked,
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


def _topic_lesson_payload(topic: TopicDefinition, level: int) -> dict[str, Any]:
    lesson = topic.lesson_for_level(level)
    return {
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


def _build_card_for_activity(game_type: str, language: str, level: int, activity_id: str) -> dict[str, Any] | None:
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

    return {
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


@app.post("/api/games/daily")
def get_daily_games(req: DailyGamesRequest) -> dict:
    logger.info(
        "daily_games learner_id=%s level_override_today=%s",
        req.learner_id,
        req.level_override_today,
    )
    state = memory.load_or_create(req.learner_id)
    prefs = memory.load_or_create_preferences(req.learner_id)
    preferred_language = prefs.preferred_language or "ja"
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
    if requested_level is None:
        today_level = current_level
    else:
        today_level = min(max(1, requested_level), 3)
    level_up_blocked = bool(requested_level is not None and requested_level > current_level)
    if level_up_blocked:
        today_level = current_level

    topic, progress, _today_iso = _daily_topic_for(learner_id=req.learner_id, language=preferred_language)
    daily_plan = topic.daily_plan_for_level(today_level)
    daily_cards: list[dict[str, Any]] = []
    for game_type, activity_id in daily_plan:
        card = _build_card_for_activity(
            game_type=game_type,
            language=preferred_language,
            level=today_level,
            activity_id=activity_id,
        )
        if card is not None:
            daily_cards.append(card)

    daily_game_types = [card["game_type"] for card in daily_cards]
    daily_progress = _daily_progress_payload(progress, daily_game_types=daily_game_types)
    extra_plan = topic.extra_plan_for_level(today_level)
    extra_cards: list[dict[str, Any]] = []
    for game_type, activity_id in extra_plan:
        card = _build_card_for_activity(
            game_type=game_type,
            language=preferred_language,
            level=today_level,
            activity_id=activity_id,
        )
        if card is not None:
            extra_cards.append(card)

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
        all_cards.append(
            {
                "game_type": game,
                "display_name": GAME_NAME_ALIASES.get(game, game),
                "activity_id": activity.activity_id,
                "language": activity.language,
                "prompt": activity.prompt,
                "level": activity.level,
                "payload": _game_payload(
                    game_type=game,
                    language=preferred_language,
                    level=today_level,
                    activity_id=activity.activity_id,
                    prompt=activity.prompt,
                ),
            }
        )

    response = _ui_state(
        learner_id=req.learner_id,
        preferred_language=preferred_language,
        difficulty=difficulty,
        today_level=today_level,
        overridden=req.level_override_today is not None,
    )
    response["topic"] = {
        "topic_key": topic.topic_key,
        "title": topic.title,
        "description": topic.description,
    }
    response["lesson"] = _topic_lesson_payload(topic=topic, level=today_level)
    response["daily_progress"] = daily_progress
    response["daily_games"] = daily_cards
    response["extra_games"] = extra_cards
    response["level_up_blocked"] = level_up_blocked
    response["selected_game"] = selected_game
    response["available_games"] = available_cards
    response["all_games"] = all_cards
    logger.info(
        "daily_games_ready learner_id=%s language=%s topic=%s current_level=%s today_level=%s selected_game=%s daily=%s extras=%s available=%s all=%s lesson_completed=%s level_up_blocked=%s",
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
        daily_progress["lesson_completed"],
        level_up_blocked,
    )
    return response


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
    daily_game_types = [game_type for game_type, _activity_id in topic.daily_plan_for_level(current_level)]
    daily_progress = _daily_progress_payload(progress, daily_game_types=daily_game_types)
    logger.info(
        "lesson_complete learner_id=%s language=%s topic=%s",
        learner_id,
        language,
        topic.topic_key,
    )
    return {
        "saved": True,
        "topic_key": topic.topic_key,
        "daily_progress": daily_progress,
    }


@app.post("/api/ui/language")
def update_ui_language(req: LanguageUpdateRequest) -> dict:
    language = req.language.strip().lower()
    if language not in AVAILABLE_LANGUAGES:
        logger.warning("ui_language_invalid learner_id=%s requested=%s", req.learner_id, language)
        return {"error": f"Unsupported language: {language}"}

    memory.load_or_create(req.learner_id)
    prefs = memory.load_or_create_preferences(req.learner_id)
    levels = prefs.levels()
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
    daily_game_types = list(daily_plan.keys())
    return _daily_progress_payload(progress, daily_game_types=daily_game_types)


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
    service = game_services.get(req.game_type)
    if service is None:
        logger.warning("game_eval_unsupported game_type=%s", req.game_type)
        return {"error": f"Unsupported game: {req.game_type}"}

    try:
        if req.game_type == GAME_TYPE_GRAMMAR_PARTICLE_FIX:
            result = service.evaluate_attempt(
                GrammarParticleAttempt(
                    language=req.language,
                    item_id=req.payload.get("item_id", ""),
                    selected_particle=req.payload.get("selected_particle", ""),
                    level=req.level,
                )
            )
        elif req.game_type == GAME_TYPE_SENTENCE_ORDER:
            result = service.evaluate_attempt(
                SentenceOrderAttempt(
                    language=req.language,
                    item_id=req.payload.get("item_id", ""),
                    ordered_tokens_by_user=req.payload.get("ordered_tokens_by_user", []),
                    level=req.level,
                )
            )
        elif req.game_type == GAME_TYPE_LISTENING_GAP_FILL:
            result = service.evaluate_attempt(
                ListeningGapFillAttempt(
                    language=req.language,
                    item_id=req.payload.get("item_id", ""),
                    user_gap_tokens=req.payload.get("user_gap_tokens", []),
                    level=req.level,
                )
            )
        elif req.game_type == GAME_TYPE_MORA_ROMANIZATION:
            result = service.evaluate_attempt(
                MoraRomanizationAttempt(
                    language=req.language,
                    item_id=req.payload.get("item_id", ""),
                    user_romanized_text=req.payload.get("user_romanized_text", ""),
                    level=req.level,
                )
            )
        elif req.game_type == GAME_TYPE_CONTEXT_QUIZ:
            result = service.evaluate_attempt(
                ContextQuizAttempt(
                    language=req.language,
                    item_id=req.payload.get("item_id", ""),
                    selected_option_id=req.payload.get("selected_option_id", ""),
                    level=req.level,
                )
            )
        elif req.game_type == GAME_TYPE_KANJI_MATCH:
            pairs = service.get_pairs(language=req.language, level=req.level)
            result = service.evaluate_attempt(
                KanjiMatchAttempt(
                    language=req.language,
                    expected_pairs=pairs,
                    learner_readings=req.payload.get("learner_readings", {}),
                    learner_meanings=req.payload.get("learner_meanings", req.payload.get("learner_matches", {})),
                    learner_matches=req.payload.get("learner_matches", {}),
                    level=req.level,
                )
            )
        elif req.game_type == ALIAS_GAME_TYPE_KANA_SPEED_ROUND:
            result = service.evaluate_attempt(
                ScriptSpeedAttempt(
                    language=req.language,
                    sequence_expected=req.payload.get("sequence_expected", []),
                    sequence_read=req.payload.get("sequence_read", []),
                    elapsed_seconds=float(req.payload.get("elapsed_seconds", 1.0)),
                    level=req.level,
                    expected_text=req.payload.get("expected_text", ""),
                    recognized_text=req.payload.get("recognized_text", ""),
                    audio_duration_seconds=float(req.payload.get("audio_duration_seconds", req.payload.get("elapsed_seconds", 1.0))),
                    speech_seconds=float(req.payload.get("speech_seconds", req.payload.get("elapsed_seconds", 1.0))),
                    pause_seconds=float(req.payload.get("pause_seconds", 0.2)),
                    pitch_track_hz=req.payload.get("pitch_track_hz", [150.0, 149.0, 151.0]),
                    retry_count=req.retry_count,
                )
            )
        elif req.game_type == GAME_TYPE_PRONUNCIATION_MATCH:
            result = service.evaluate_attempt(
                PronunciationMatchAttempt(
                    language=req.language,
                    expected_text=req.payload.get("expected_text", ""),
                    recognized_text=req.payload.get("recognized_text", ""),
                    audio_duration_seconds=float(req.payload.get("audio_duration_seconds", 2.0)),
                    speech_seconds=float(req.payload.get("speech_seconds", 1.8)),
                    pause_seconds=float(req.payload.get("pause_seconds", 0.2)),
                    pitch_track_hz=req.payload.get("pitch_track_hz", [150.0, 151.0, 149.0]),
                    item_id=req.payload.get("item_id", ""),
                    level=req.level,
                    retry_count=req.retry_count,
                )
            )
        else:
            result = {"error": f"Evaluation not implemented for: {req.game_type}"}
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
        if item_id:
            daily_progress = _mark_daily_game_progress(
                learner_id=req.learner_id,
                language=req.language,
                level=req.level,
                game_type=req.game_type,
                item_id=item_id,
            )
            if daily_progress is not None and isinstance(result, dict):
                result["daily_progress"] = daily_progress
        score = result.get("score") if isinstance(result, dict) else None
        logger.info("game_eval_done game_type=%s score=%s", req.game_type, score)
    return result
