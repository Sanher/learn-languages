from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging

from language_games.pronunciation import PronunciationRequest, run_pronunciation_activity

from .game_service import GameActivity
from .writing_support import writing_support_profile

GAME_TYPE_PRONUNCIATION_MATCH = "pronunciation_match"
LANGUAGE_JAPANESE = "ja"
# Trazas por servicio para observar flujo y resultados en HA.
logger = logging.getLogger("learn_languages.games.pronunciation_match")

# Contenido inicial solo para japonés: texto, romanizado y traduccion aproximada.
JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL: dict[int, list[tuple[str, str, str]]] = {
    1: [
        ("おはよう ございます", "ohayou gozaimasu", "buenos dias (formal)"),
        ("ありがとうございます", "arigatou gozaimasu", "gracias (formal)"),
        ("すみません", "sumimasen", "disculpe / perdon"),
    ],
    2: [
        ("今日は いい 天気 ですね", "kyou wa ii tenki desu ne", "hoy hace buen tiempo, verdad"),
        ("もう 一度 お願い します", "mou ichido onegai shimasu", "otra vez, por favor"),
        ("水 を ください", "mizu o kudasai", "agua, por favor"),
    ],
    3: [
        (
            "日本語 の 発音 を 毎日 練習 しています",
            "nihongo no hatsuon o mainichi renshuu shiteimasu",
            "practico la pronunciacion de japones cada dia",
        ),
        (
            "この 表現 は 場面 によって 使い分けます",
            "kono hyougen wa bamen ni yotte tsukaiwakemasu",
            "esta expresion se usa segun el contexto",
        ),
    ],
}

# Compatibilidad con imports previos.
JAPANESE_PRONUNCIATION_PHRASES_BY_LEVEL: dict[int, list[str]] = {
    level: [text for text, _romanized, _translation in items]
    for level, items in JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL.items()
}

MATCH_THRESHOLD_BY_LEVEL: dict[int, float] = {
    1: 0.65,
    2: 0.72,
    3: 0.78,
}


@dataclass(frozen=True)
class PronunciationMatchAttempt:
    language: str
    expected_text: str
    recognized_text: str
    audio_duration_seconds: float
    speech_seconds: float
    pause_seconds: float
    pitch_track_hz: list[float]
    item_id: str = ""
    level: int = 1
    retry_count: int = 0


@dataclass(frozen=True)
class PronunciationItem:
    item_id: str
    text: str
    romanized_line: str
    literal_translation: str


class PronunciationMatchService:
    """Servicio reusable de match de pronunciación (ja inicial)."""

    game_type = GAME_TYPE_PRONUNCIATION_MATCH

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        if language != LANGUAGE_JAPANESE:
            logger.info("activities_skipped unsupported_language=%s", language)
            return []

        selected_level = self._normalize_level(level)
        items = self.get_items(language=language, level=selected_level)
        activities = [
            GameActivity(
                activity_id=item.item_id,
                language=LANGUAGE_JAPANESE,
                game_type=GAME_TYPE_PRONUNCIATION_MATCH,
                prompt=item.text,
                level=selected_level,
            )
            for item in items
        ]
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def get_items(self, language: str, level: int = 1) -> list[PronunciationItem]:
        if language != LANGUAGE_JAPANESE:
            return []
        selected_level = self._normalize_level(level)
        raw_items = JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL[selected_level]
        return [
            PronunciationItem(
                item_id=f"ja-pronunciation-{selected_level}-{idx + 1}",
                text=text,
                romanized_line=romanized,
                literal_translation=translation,
            )
            for idx, (text, romanized, translation) in enumerate(raw_items)
        ]

    def build_attempt_view(
        self,
        language: str,
        item_id: str,
        level: int = 1,
        show_translation: bool = False,
    ) -> dict:
        item = self._find_item(language=language, item_id=item_id, level=level)
        support = writing_support_profile(level)
        return self._view_payload(
            item=item,
            support=support,
            show_translation=show_translation,
        )

    def evaluate_attempt(self, attempt: PronunciationMatchAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s item_id=%s level=%s retry_count=%s expected_len=%s recognized_len=%s",
            attempt.language,
            attempt.item_id,
            attempt.level,
            attempt.retry_count,
            len(attempt.expected_text),
            len(attempt.recognized_text),
        )
        if attempt.language != LANGUAGE_JAPANESE:
            logger.warning("evaluate_invalid unsupported_language=%s", attempt.language)
            raise ValueError(f"Idioma no soportado en pronunciation match: {attempt.language}")

        item = self._resolve_item(
            language=attempt.language,
            item_id=attempt.item_id,
            expected_text=attempt.expected_text,
            level=attempt.level,
        )
        expected_text = item.text if item else attempt.expected_text
        result = run_pronunciation_activity(
            request=PronunciationRequest(
                expected_text=expected_text,
                recognized_text=attempt.recognized_text,
                audio_duration_seconds=attempt.audio_duration_seconds,
                speech_seconds=attempt.speech_seconds,
                pause_seconds=attempt.pause_seconds,
                pitch_track_hz=attempt.pitch_track_hz,
                activity_type=self.game_type,
                language=attempt.language,
            ),
            current_date=date.today(),
        )

        threshold = MATCH_THRESHOLD_BY_LEVEL.get(attempt.level, MATCH_THRESHOLD_BY_LEVEL[1])
        confidence = result["metrics"]["pronunciation_confidence"]
        alerts: list[str] = []
        if attempt.retry_count >= 3:
            alerts.append(
                "Aviso: desde el 3er reintento puede aumentar el consumo de tokens STT/TTS."
            )

        result["match_threshold"] = threshold
        result["is_match"] = confidence >= threshold
        result["retry_count"] = attempt.retry_count
        result["retry_available"] = True
        result["alerts"] = alerts

        if item is not None:
            support = writing_support_profile(attempt.level)
            result["literal_translation"] = item.literal_translation
            result["display"] = self._view_payload(
                item=item,
                support=support,
                show_translation=True,
            )
            result["retry_state"] = self._view_payload(
                item=item,
                support=support,
                show_translation=False,
            )

        logger.info(
            "evaluate_done language=%s item_id=%s level=%s retry_count=%s score=%s is_match=%s confidence=%.2f threshold=%.2f",
            attempt.language,
            attempt.item_id,
            attempt.level,
            attempt.retry_count,
            result.get("score"),
            result["is_match"],
            confidence,
            threshold,
        )
        return result

    @staticmethod
    def _normalize_level(level: int) -> int:
        max_level = max(JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL.keys())
        return min(max(1, level), max_level)

    def _find_item(self, language: str, item_id: str, level: int) -> PronunciationItem:
        if language != LANGUAGE_JAPANESE:
            raise ValueError(f"Idioma no soportado en pronunciation match: {language}")

        for item in self.get_items(language=language, level=level):
            if item.item_id == item_id:
                return item
        for candidate_level in sorted(JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL):
            for item in self.get_items(language=language, level=candidate_level):
                if item.item_id == item_id:
                    return item
        raise ValueError(f"item_id no encontrado para language={language}, level={level}: {item_id}")

    def _resolve_item(self, language: str, item_id: str, expected_text: str, level: int) -> PronunciationItem | None:
        if language != LANGUAGE_JAPANESE:
            return None

        if item_id:
            try:
                return self._find_item(language=language, item_id=item_id, level=level)
            except ValueError:
                logger.warning("resolve_item_missing item_id=%s language=%s level=%s", item_id, language, level)

        normalized_expected = (expected_text or "").strip()
        if not normalized_expected:
            return None

        for candidate_level in sorted(JAPANESE_PRONUNCIATION_ITEMS_BY_LEVEL):
            for item in self.get_items(language=language, level=candidate_level):
                if item.text == normalized_expected:
                    return item
        return None

    @staticmethod
    def _view_payload(item: PronunciationItem, support, show_translation: bool) -> dict:
        show_romanized = bool(support.show_romanized_line and item.romanized_line)
        return {
            "show_romanized_line": show_romanized,
            "romanized_line": item.romanized_line if show_romanized else None,
            "show_translation_hint": False,
            "translation_hint": None,
            "show_literal_translation": show_translation,
            "literal_translation": item.literal_translation if show_translation else None,
            "retry_available": True,
        }
