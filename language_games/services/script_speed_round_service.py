from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging

from language_games.pronunciation import PronunciationRequest, run_pronunciation_activity

from .game_service import GameActivity
from .writing_support import writing_support_profile

GAME_TYPE_SCRIPT_SPEED_ROUND = "script_speed_round"
ALIAS_GAME_TYPE_KANA_SPEED_ROUND = "kana_speed_round"
# Trazas por servicio para observar flujo y resultados en HA.
logger = logging.getLogger("learn_languages.games.script_speed_round")

LANGUAGE_JAPANESE = "ja"
LANGUAGE_ENGLISH = "en"
LANGUAGE_SPANISH = "es"


@dataclass(frozen=True)
class ScriptSpeedProfile:
    language: str
    script_label: str
    characters_by_level: dict[int, list[str]]
    target_items_per_minute_by_level: dict[int, tuple[float, float]]


@dataclass(frozen=True)
class ScriptSpeedAttempt:
    language: str
    sequence_expected: list[str]
    sequence_read: list[str]
    elapsed_seconds: float
    level: int = 1
    expected_text: str = ""
    recognized_text: str = ""
    audio_duration_seconds: float = 0.0
    speech_seconds: float = 0.0
    pause_seconds: float = 0.0
    pitch_track_hz: list[float] | None = None
    retry_count: int = 0


JAPANESE_KANA_BY_LEVEL: dict[int, list[str]] = {
    1: ["あ", "い", "う", "え", "お", "か", "き", "く", "け", "こ"],
    2: ["さ", "し", "す", "せ", "そ", "た", "ち", "つ", "て", "と"],
    3: ["な", "に", "ぬ", "ね", "の", "は", "ひ", "ふ", "へ", "ほ"],
}

KANA_ROMAJI_MAP: dict[str, str] = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
}
_JAPANESE_PUNCTUATION = {" ", "　", "、", "。", "！", "？", "・", ",", ".", "!", "?"}

LATIN_CHARACTERS_BY_LEVEL: dict[int, list[str]] = {
    1: list("abcdefghij"),
    2: list("klmnopqrst"),
    3: list("uvwxyz"),
}

TARGET_ITEMS_PER_MINUTE_JA: dict[int, tuple[float, float]] = {
    1: (35.0, 85.0),
    2: (45.0, 95.0),
    3: (55.0, 105.0),
}

TARGET_ITEMS_PER_MINUTE_LATIN: dict[int, tuple[float, float]] = {
    1: (45.0, 95.0),
    2: (55.0, 105.0),
    3: (65.0, 115.0),
}


class ScriptSpeedRoundService:
    """Servicio reusable de lectura rapida por sistema de escritura."""

    def __init__(self, game_type: str = GAME_TYPE_SCRIPT_SPEED_ROUND, allowed_languages: set[str] | None = None) -> None:
        self.game_type = game_type
        self.allowed_languages = allowed_languages
        self._profiles = self._default_profiles()

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request game_type=%s language=%s level=%s", self.game_type, language, level)
        if self.allowed_languages is not None and language not in self.allowed_languages:
            logger.info("activities_skipped game_type=%s language_not_allowed=%s", self.game_type, language)
            return []

        profile = self._profiles.get(language)
        if profile is None:
            logger.info("activities_skipped game_type=%s unsupported_language=%s", self.game_type, language)
            return []

        normalized_level = self._normalize_level(level, profile.characters_by_level)
        support = writing_support_profile(level)
        chars = profile.characters_by_level[normalized_level]
        chunks = self._chunk(chars, 5)

        activities: list[GameActivity] = []
        for idx, chunk in enumerate(chunks, start=1):
            sequence = " ".join(chunk)
            lines = [f"Lee rapido ({profile.script_label}): {sequence}"]
            if language == LANGUAGE_JAPANESE and support.show_romanized_line:
                romaji = " ".join(KANA_ROMAJI_MAP.get(ch, ch) for ch in chunk)
                lines.append(f"Guia romaji: {romaji}")
            activities.append(
                GameActivity(
                    activity_id=f"{language}-{self.game_type}-{normalized_level}-{idx}",
                    language=language,
                    game_type=self.game_type,
                    prompt="\n".join(lines),
                    level=normalized_level,
                )
            )
        logger.info(
            "activities_ready game_type=%s language=%s level=%s normalized_level=%s count=%s",
            self.game_type,
            language,
            level,
            normalized_level,
            len(activities),
        )
        return activities

    def evaluate_attempt(self, attempt: ScriptSpeedAttempt) -> dict:
        logger.info(
            "evaluate_start game_type=%s language=%s level=%s retry_count=%s expected_len=%s recognized_len=%s",
            self.game_type,
            attempt.language,
            attempt.level,
            attempt.retry_count,
            len(attempt.expected_text),
            len(attempt.recognized_text),
        )
        if self.allowed_languages is not None and attempt.language not in self.allowed_languages:
            logger.warning("evaluate_invalid game_type=%s language_not_allowed=%s", self.game_type, attempt.language)
            raise ValueError(f"Idioma no soportado en {self.game_type}: {attempt.language}")

        profile = self._profiles.get(attempt.language)
        if profile is None:
            logger.warning("evaluate_invalid game_type=%s unsupported_language=%s", self.game_type, attempt.language)
            raise ValueError(f"Idioma no soportado en {self.game_type}: {attempt.language}")

        normalized_level = self._normalize_level(attempt.level, profile.characters_by_level)
        expected_tokens = attempt.sequence_expected or self._tokenize_text(attempt.expected_text, attempt.language)
        read_tokens = attempt.sequence_read or self._tokenize_text(attempt.recognized_text, attempt.language)

        pronunciation_metrics: dict[str, float] | None = None
        accuracy = self._position_accuracy(expected_tokens, read_tokens)
        if attempt.expected_text or attempt.recognized_text:
            audio_duration = max(0.1, attempt.audio_duration_seconds or attempt.elapsed_seconds or 1.0)
            speech_seconds = max(0.1, attempt.speech_seconds or attempt.elapsed_seconds or audio_duration)
            pronunciation = run_pronunciation_activity(
                request=PronunciationRequest(
                    expected_text=attempt.expected_text or " ".join(expected_tokens),
                    recognized_text=attempt.recognized_text or " ".join(read_tokens),
                    audio_duration_seconds=audio_duration,
                    speech_seconds=speech_seconds,
                    pause_seconds=max(0.0, attempt.pause_seconds),
                    pitch_track_hz=attempt.pitch_track_hz or [150.0, 149.0, 151.0],
                    activity_type=self.game_type,
                    language=attempt.language,
                ),
                current_date=date.today(),
            )
            accuracy = pronunciation["metrics"]["pronunciation_confidence"]
            pronunciation_metrics = pronunciation["metrics"]

        pace_items_count = len(read_tokens) or len(self._tokenize_text(attempt.recognized_text, attempt.language))
        elapsed_seconds = attempt.elapsed_seconds or attempt.speech_seconds or attempt.audio_duration_seconds
        pace_score = self._pace_score(
            items_count=pace_items_count,
            elapsed_seconds=elapsed_seconds,
            target_range=profile.target_items_per_minute_by_level[normalized_level],
        )
        # Priorizamos exactitud de lectura frente a velocidad para evitar subir score por ir demasiado rapido.
        score = round(((accuracy * 0.75) + (pace_score * 0.25)) * 100)

        alerts: list[str] = []
        if attempt.retry_count >= 3:
            alerts.append("Aviso: desde el 3er reintento puede aumentar el consumo de tokens STT/TTS.")

        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "score": max(0, min(100, score)),
            "metrics": {
                "accuracy": round(accuracy, 2),
                "pace_score": round(pace_score, 2),
            },
            "retry_count": attempt.retry_count,
            "retry_available": True,
            "alerts": alerts,
        }
        if pronunciation_metrics is not None:
            result["metrics"]["pronunciation_confidence"] = pronunciation_metrics["pronunciation_confidence"]
            result["metrics"]["speech_rate_wpm"] = pronunciation_metrics["speech_rate_wpm"]
            result["metrics"]["pause_ratio"] = pronunciation_metrics["pause_ratio"]
            result["metrics"]["pitch_stability"] = pronunciation_metrics["pitch_stability"]
        logger.info(
            "evaluate_done game_type=%s language=%s level=%s retry_count=%s score=%s accuracy=%.2f pace=%.2f",
            self.game_type,
            attempt.language,
            attempt.level,
            attempt.retry_count,
            result["score"],
            accuracy,
            pace_score,
        )
        return result

    @staticmethod
    def _default_profiles() -> dict[str, ScriptSpeedProfile]:
        return {
            LANGUAGE_JAPANESE: ScriptSpeedProfile(
                language=LANGUAGE_JAPANESE,
                script_label="kana",
                characters_by_level=JAPANESE_KANA_BY_LEVEL,
                target_items_per_minute_by_level=TARGET_ITEMS_PER_MINUTE_JA,
            ),
            LANGUAGE_ENGLISH: ScriptSpeedProfile(
                language=LANGUAGE_ENGLISH,
                script_label="latin",
                characters_by_level=LATIN_CHARACTERS_BY_LEVEL,
                target_items_per_minute_by_level=TARGET_ITEMS_PER_MINUTE_LATIN,
            ),
            LANGUAGE_SPANISH: ScriptSpeedProfile(
                language=LANGUAGE_SPANISH,
                script_label="latin",
                characters_by_level=LATIN_CHARACTERS_BY_LEVEL,
                target_items_per_minute_by_level=TARGET_ITEMS_PER_MINUTE_LATIN,
            ),
        }

    @staticmethod
    def _normalize_level(level: int, data: dict[int, list[str]]) -> int:
        minimum = min(data.keys())
        maximum = max(data.keys())
        return min(max(minimum, level), maximum)

    @staticmethod
    def _chunk(items: list[str], size: int) -> list[list[str]]:
        return [items[i : i + size] for i in range(0, len(items), size)]

    @staticmethod
    def _tokenize_text(text: str, language: str) -> list[str]:
        if " " in text:
            return [token for token in text.split() if token]
        if language == LANGUAGE_JAPANESE:
            return [ch for ch in text if ch not in _JAPANESE_PUNCTUATION]
        return [token for token in text.split() if token]

    @staticmethod
    def _position_accuracy(expected: list[str], read: list[str]) -> float:
        if not expected:
            return 0.0
        comparisons = min(len(expected), len(read))
        if comparisons == 0:
            return 0.0
        hits = sum(1 for i in range(comparisons) if expected[i] == read[i])
        return hits / len(expected)

    @staticmethod
    def _pace_score(items_count: int, elapsed_seconds: float, target_range: tuple[float, float]) -> float:
        if elapsed_seconds <= 0:
            return 0.0
        items_per_minute = (items_count / elapsed_seconds) * 60.0
        target_min, target_max = target_range
        if target_min <= items_per_minute <= target_max:
            return 1.0
        if items_per_minute < target_min:
            return max(0.0, 1 - ((target_min - items_per_minute) / target_min))
        return max(0.0, 1 - ((items_per_minute - target_max) / max(target_max, 1.0)))


class KanaSpeedRoundService(ScriptSpeedRoundService):
    """Alias compatible: kana_speed_round para japones."""

    def __init__(self) -> None:
        super().__init__(
            game_type=ALIAS_GAME_TYPE_KANA_SPEED_ROUND,
            allowed_languages={LANGUAGE_JAPANESE},
        )
