from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from .runtime_config import get_setting

logger = logging.getLogger("learn_languages.japanese.openai")
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


class OpenAIPlanner:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or get_setting(
            env_names=("OPENAI_API_KEY",),
            option_names=("openai_api_key", "openai.key", "openai.api_key"),
            default="",
        )
        self.model = model or get_setting(
            env_names=("OPENAI_MODEL",),
            option_names=("openai_model", "openai.model"),
            default="gpt-4o-mini",
        )
        raw_stt_models = get_setting(
            env_names=("OPENAI_STT_MODELS",),
            option_names=("openai_stt_models", "openai.stt_models", "openai.stt.models"),
            default="gpt-4o-mini-transcribe,whisper-1",
        )
        self.stt_models = [model_name.strip() for model_name in raw_stt_models.split(",") if model_name.strip()]
        # Short timeout and circuit breaker for translation calls to avoid cascading latency/cost.
        timeout_raw = get_setting(
            env_names=("OPENAI_TRANSLATION_TIMEOUT_SECONDS",),
            option_names=("openai_translation_timeout_seconds", "openai.translation_timeout_seconds"),
            default="12",
        )
        threshold_raw = get_setting(
            env_names=("OPENAI_TRANSLATION_FAILURE_THRESHOLD",),
            option_names=("openai_translation_failure_threshold", "openai.translation_failure_threshold"),
            default="3",
        )
        cooldown_raw = get_setting(
            env_names=("OPENAI_TRANSLATION_COOLDOWN_SECONDS",),
            option_names=("openai_translation_cooldown_seconds", "openai.translation_cooldown_seconds"),
            default="180",
        )
        try:
            self.translation_timeout_seconds = max(2.0, float(timeout_raw))
        except (TypeError, ValueError):
            self.translation_timeout_seconds = 12.0
        try:
            self.translation_failure_threshold = max(1, int(threshold_raw))
        except (TypeError, ValueError):
            self.translation_failure_threshold = 3
        try:
            self.translation_cooldown_seconds = max(30, int(cooldown_raw))
        except (TypeError, ValueError):
            self.translation_cooldown_seconds = 180
        max_chars_raw = get_setting(
            env_names=("OPENAI_TRANSLATION_MAX_TEXT_CHARS",),
            option_names=("openai_translation_max_text_chars", "openai.translation_max_text_chars"),
            default="900",
        )
        max_context_raw = get_setting(
            env_names=("OPENAI_TRANSLATION_MAX_CONTEXT_CHARS",),
            option_names=("openai_translation_max_context_chars", "openai.translation_max_context_chars"),
            default="240",
        )
        try:
            self.translation_max_text_chars = max(60, int(max_chars_raw))
        except (TypeError, ValueError):
            self.translation_max_text_chars = 900
        try:
            self.translation_max_context_chars = max(20, int(max_context_raw))
        except (TypeError, ValueError):
            self.translation_max_context_chars = 240
        self._translation_consecutive_failures = 0
        self._translation_circuit_open_until = 0.0

    def _fallback_daily_activities(self, *, difficulty: int, games: list[str]) -> list[dict[str, str]]:
        ordered_games: list[str] = []
        seen: set[str] = set()
        for game in games:
            normalized = str(game or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_games.append(normalized)
        return [
            {
                "game": game,
                "prompt": f"Level {difficulty}: {game} exercise for Japanese.",
            }
            for game in ordered_games
        ]

    def _is_translation_circuit_open(self) -> bool:
        return time.monotonic() < self._translation_circuit_open_until

    def _mark_translation_success(self) -> None:
        if self._translation_consecutive_failures:
            logger.info(
                "translation_recovered consecutive_failures=%s",
                self._translation_consecutive_failures,
            )
        self._translation_consecutive_failures = 0
        self._translation_circuit_open_until = 0.0

    def _mark_translation_failure(self, *, reason: str) -> None:
        self._translation_consecutive_failures += 1
        logger.warning(
            "translation_failure consecutive_failures=%s threshold=%s reason=%s",
            self._translation_consecutive_failures,
            self.translation_failure_threshold,
            reason,
        )
        if self._translation_consecutive_failures < self.translation_failure_threshold:
            return
        self._translation_circuit_open_until = time.monotonic() + float(self.translation_cooldown_seconds)
        logger.warning(
            "translation_circuit_open cooldown_seconds=%s",
            self.translation_cooldown_seconds,
        )

    def translate_text(
        self,
        *,
        source_text: str,
        target_language: str,
        source_language: str = "en",
        context: str = "",
    ) -> dict[str, Any]:
        text = str(source_text or "").strip()
        target = str(target_language or "").strip().lower()
        source = str(source_language or "en").strip().lower()
        if not text:
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "Empty source text for translation.",
            }
        if len(text) > self.translation_max_text_chars:
            logger.warning(
                "translation_skipped_text_too_long chars=%s max=%s",
                len(text),
                self.translation_max_text_chars,
            )
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "Source text is too long for translation.",
            }
        if not target:
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "Missing target language for translation.",
            }
        if not self.api_key:
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "OPENAI_API_KEY is not configured for translation.",
            }
        if self._is_translation_circuit_open():
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "Translation temporarily unavailable due to repeated provider failures.",
            }

        system_prompt = (
            "You are a precise translator for language-learning content. "
            "Translate the input text to the requested target language. "
            "Preserve Japanese script, romaji, punctuation, and line breaks when present. "
            "Return plain text only."
        )
        user_prompt = (
            f"Source language: {source}\n"
            f"Target language: {target}\n"
            f"Context: {str(context or 'general').strip()[: self.translation_max_context_chars]}\n"
            f"Text:\n{text}"
        )

        try:
            with httpx.Client(timeout=self.translation_timeout_seconds) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": [
                            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
                        ],
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            self._mark_translation_failure(reason=type(exc).__name__)
            return {
                "source": "fallback",
                "translated_text": "",
                "error": f"Translation request failed: {type(exc).__name__}",
            }

        translated_text = ""
        for block in payload.get("output", []):
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    translated_text += item.get("text", "")

        normalized_output = translated_text.strip()
        if not normalized_output:
            self._mark_translation_failure(reason="empty_output")
            return {
                "source": "fallback",
                "translated_text": "",
                "error": "Empty translation output.",
            }
        self._mark_translation_success()
        return {
            "source": "openai",
            "translated_text": normalized_output,
        }

    async def generate_daily_content(self, *, difficulty: int, games: list[str], learner_note: str) -> dict[str, Any]:
        fallback_activities = self._fallback_daily_activities(difficulty=difficulty, games=games)
        if not self.api_key:
            return {
                "source": "fallback",
                "activities": fallback_activities,
            }

        system_prompt = (
            "You are a Japanese tutor. Generate short, fun, progressive activities. "
            "Return valid JSON with key 'activities'."
        )
        user_prompt = (
            f"Difficulty {difficulty}/10. Games: {games}. "
            f"Learner notes: {learner_note}."
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": [
                            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
                        ],
                        "text": {"format": {"type": "json_object"}},
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("daily_content_provider_error detail=%s", type(exc).__name__)
            return {
                "source": "fallback",
                "activities": fallback_activities,
                "error": f"Daily content request failed: {type(exc).__name__}",
            }

        text_outputs = payload.get("output", [])
        content_text = ""
        for block in text_outputs:
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    content_text += item.get("text", "")

        raw_text = content_text.strip()
        if not raw_text:
            logger.warning("daily_content_empty_output")
            return {
                "source": "fallback",
                "activities": fallback_activities,
                "error": "Empty daily content output.",
            }

        # Providers sometimes wrap JSON with extra prose/markdown; keep only the outermost JSON object.
        json_candidate = raw_text
        first_brace = json_candidate.find("{")
        last_brace = json_candidate.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            json_candidate = json_candidate[first_brace : last_brace + 1]

        try:
            parsed = json.loads(json_candidate)
        except json.JSONDecodeError:
            logger.warning("daily_content_invalid_json")
            return {
                "source": "fallback",
                "activities": fallback_activities,
                "raw": raw_text,
                "error": "Invalid JSON daily content output.",
            }

        parsed_activities = parsed.get("activities")
        if not isinstance(parsed_activities, list):
            logger.warning("daily_content_missing_activities")
            return {
                "source": "fallback",
                "activities": fallback_activities,
                "raw": raw_text,
                "error": "Missing activities in daily content output.",
            }

        requested_order = [item["game"] for item in fallback_activities]
        requested_set = set(requested_order)
        prompts_by_game: dict[str, str] = {}
        for row in parsed_activities:
            if not isinstance(row, dict):
                continue
            game = str(row.get("game") or "").strip()
            prompt = str(row.get("prompt") or "").strip()
            if not game or not prompt or game not in requested_set or game in prompts_by_game:
                continue
            prompts_by_game[game] = prompt

        if not prompts_by_game:
            logger.warning("daily_content_no_valid_prompts")
            return {
                "source": "fallback",
                "activities": fallback_activities,
                "raw": raw_text,
                "error": "No valid prompts in daily content output.",
            }

        activities: list[dict[str, str]] = []
        fallback_by_game = {row["game"]: row["prompt"] for row in fallback_activities}
        for game in requested_order:
            activities.append(
                {
                    "game": game,
                    "prompt": prompts_by_game.get(game, fallback_by_game.get(game, "")),
                }
            )

        logger.info(
            "daily_content_generated requested=%s resolved=%s model=%s",
            len(requested_order),
            len(prompts_by_game),
            self.model,
        )
        return {
            "source": "openai",
            "activities": activities,
            "raw": raw_text,
        }

    async def generate_extra_game_prompt(
        self,
        *,
        language: str,
        topic_title: str,
        game_type: str,
        level: int,
    ) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": "fallback",
                "text": f"Topic: {topic_title}. Try this {game_type} activity at level {level}.",
            }

        system_prompt = (
            "You are a language-learning tutor. "
            "Generate exactly one short activity prompt in English for the given game type and level. "
            "Keep it concise (max 22 words) and practical."
        )
        user_prompt = (
            f"Language={language}. Topic={topic_title}. Game={game_type}. Level={level}. "
            "Return plain text only."
        )

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()

        text_outputs = payload.get("output", [])
        content_text = ""
        for block in text_outputs:
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    content_text += item.get("text", "")

        return {
            "source": "openai",
            "text": content_text.strip(),
        }

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        mime_type: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": "fallback",
                "transcript": "",
                "error": "OPENAI_API_KEY is not configured for STT.",
            }

        if not audio_bytes:
            return {
                "source": "fallback",
                "transcript": "",
                "error": "Empty audio payload.",
            }

        errors: list[str] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for stt_model in self.stt_models:
                data: dict[str, str] = {"model": stt_model}
                if language:
                    data["language"] = language
                files = {
                    "file": (filename, audio_bytes, mime_type),
                }
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        data=data,
                        files=files,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    transcript = (payload.get("text") or payload.get("transcript") or "").strip()
                    return {
                        "source": "openai",
                        "model": stt_model,
                        "transcript": transcript,
                    }
                except httpx.HTTPStatusError as exc:
                    errors.append(f"{stt_model}: HTTP {exc.response.status_code}")
                except Exception as exc:  # pragma: no cover - defensive for network/provider edge cases
                    errors.append(f"{stt_model}: {type(exc).__name__}")

        return {
            "source": "fallback",
            "transcript": "",
            "error": "Audio transcription failed.",
            "details": errors,
        }
