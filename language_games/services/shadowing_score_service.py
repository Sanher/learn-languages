from __future__ import annotations

from dataclasses import dataclass
import logging

from .game_service import GameActivity
from .writing_support import writing_support_profile

LANGUAGE_JAPANESE = "ja"
GAME_TYPE_SHADOWING_SCORE = "shadowing_score"
# Trazas por servicio para observar flujo y resultados en HA.
logger = logging.getLogger("learn_languages.games.shadowing_score")

# Por ahora solo se definen frases semilla para japonés.
JAPANESE_SHADOWING_ITEMS_BY_LEVEL: dict[int, list[tuple[str, str]]] = {
    1: [
        ("おはよう ございます", "ohayou gozaimasu"),
        ("ありがとうございます", "arigatou gozaimasu"),
        ("はじめまして", "hajimemashite"),
    ],
    2: [
        ("今日は いい 天気 ですね", "kyou wa ii tenki desu ne"),
        ("もう 一度 お願い します", "mou ichido onegai shimasu"),
        ("駅 は どこ ですか", "eki wa doko desu ka"),
    ],
    3: [
        ("昨日 は 仕事 が 忙しかった です", "kinou wa shigoto ga isogashikatta desu"),
        ("日本語 の 発音 を 練習 しています", "nihongo no hatsuon o renshuu shiteimasu"),
    ],
}

# Compatibilidad con imports previos.
JAPANESE_SHADOWING_PHRASES_BY_LEVEL: dict[int, list[str]] = {
    level: [text for text, _romanized in items]
    for level, items in JAPANESE_SHADOWING_ITEMS_BY_LEVEL.items()
}

JAPANESE_TARGET_CHARS_PER_SECOND_BY_LEVEL: dict[int, tuple[float, float]] = {
    1: (1.8, 4.2),
    2: (2.0, 4.8),
    3: (2.3, 5.2),
}

_JP_PUNCTUATION = {" ", "　", "、", "。", "！", "？", "・", ",", ".", "!", "?"}


@dataclass(frozen=True)
class ShadowingAttempt:
    language: str
    expected_text: str
    learner_text: str
    audio_duration_seconds: float
    pause_seconds: float
    level: int = 1
    retry_count: int = 0


@dataclass(frozen=True)
class ShadowingItem:
    item_id: str
    text: str
    romanized_line: str


class ShadowingScoreService:
    """Servicio reusable de shadowing score (implementación ja inicial)."""

    game_type = GAME_TYPE_SHADOWING_SCORE

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
                game_type=self.game_type,
                prompt=item.text,
                level=selected_level,
            )
            for item in items
        ]
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def get_items(self, language: str, level: int = 1) -> list[ShadowingItem]:
        if language != LANGUAGE_JAPANESE:
            return []
        selected_level = self._normalize_level(level)
        raw_items = JAPANESE_SHADOWING_ITEMS_BY_LEVEL[selected_level]
        return [
            ShadowingItem(
                item_id=f"ja-shadowing-{selected_level}-{idx + 1}",
                text=text,
                romanized_line=romanized,
            )
            for idx, (text, romanized) in enumerate(raw_items)
        ]

    def build_attempt_view(self, language: str, item_id: str, level: int = 1) -> dict:
        item = self._find_item(language=language, item_id=item_id, level=level)
        support = writing_support_profile(level)
        show_romanized = bool(support.show_romanized_line and item.romanized_line)
        return {
            "show_romanized_line": show_romanized,
            "romanized_line": item.romanized_line if show_romanized else None,
            "retry_available": True,
        }

    def evaluate_attempt(self, attempt: ShadowingAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s retry_count=%s expected_len=%s learner_len=%s",
            attempt.language,
            attempt.level,
            attempt.retry_count,
            len(attempt.expected_text),
            len(attempt.learner_text),
        )
        if attempt.language != LANGUAGE_JAPANESE:
            logger.warning("evaluate_invalid unsupported_language=%s", attempt.language)
            raise ValueError(f"Idioma no soportado en shadowing score: {attempt.language}")

        expected_units = self._tokenize_japanese(attempt.expected_text)
        learner_units = self._tokenize_japanese(attempt.learner_text)

        overlap = self._overlap(expected_units, learner_units)
        pace_score = self._pace_score_for_japanese(
            unit_count=len(learner_units),
            speech_seconds=max(0.1, attempt.audio_duration_seconds - attempt.pause_seconds),
            level=attempt.level,
        )
        pause_ratio = 0.0
        if attempt.audio_duration_seconds > 0:
            pause_ratio = min(1.0, max(0.0, attempt.pause_seconds / attempt.audio_duration_seconds))

        score = round(((overlap * 0.7) + (pace_score * 0.2) + ((1 - pause_ratio) * 0.1)) * 100)
        alerts: list[str] = []
        if attempt.retry_count >= 3:
            alerts.append(
                "Aviso: desde el 3er reintento puede aumentar el consumo de tokens STT/TTS."
            )

        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "score": max(0, min(100, score)),
            "metrics": {
                "text_overlap": round(overlap, 2),
                "pace_score": round(pace_score, 2),
                "pause_ratio": round(pause_ratio, 2),
            },
            "feedback": self._feedback_for_japanese(overlap=overlap, pace_score=pace_score, pause_ratio=pause_ratio),
            "retry_count": attempt.retry_count,
            "retry_available": True,
            "alerts": alerts,
        }
        logger.info(
            "evaluate_done language=%s level=%s retry_count=%s score=%s overlap=%.2f pace=%.2f pause_ratio=%.2f",
            attempt.language,
            attempt.level,
            attempt.retry_count,
            result["score"],
            overlap,
            pace_score,
            pause_ratio,
        )
        return result

    @staticmethod
    def _normalize_level(level: int) -> int:
        max_level = max(JAPANESE_SHADOWING_ITEMS_BY_LEVEL.keys())
        return min(max(1, level), max_level)

    def _find_item(self, language: str, item_id: str, level: int) -> ShadowingItem:
        if language != LANGUAGE_JAPANESE:
            raise ValueError(f"Idioma no soportado en shadowing score: {language}")

        for item in self.get_items(language=language, level=level):
            if item.item_id == item_id:
                return item
        for candidate_level in sorted(JAPANESE_SHADOWING_ITEMS_BY_LEVEL):
            for item in self.get_items(language=language, level=candidate_level):
                if item.item_id == item_id:
                    return item
        raise ValueError(f"item_id no encontrado para language={language}, level={level}: {item_id}")

    @staticmethod
    def _tokenize_japanese(text: str) -> list[str]:
        if " " in text:
            return [token for token in text.split() if token]
        return [ch for ch in text if ch not in _JP_PUNCTUATION]

    @staticmethod
    def _overlap(expected_units: list[str], learner_units: list[str]) -> float:
        if not expected_units:
            return 0.0
        learner_set = set(learner_units)
        hits = sum(1 for unit in expected_units if unit in learner_set)
        return hits / len(expected_units)

    @staticmethod
    def _pace_score_for_japanese(unit_count: int, speech_seconds: float, level: int) -> float:
        target_min, target_max = JAPANESE_TARGET_CHARS_PER_SECOND_BY_LEVEL.get(level, (1.8, 4.2))
        cps = unit_count / max(0.1, speech_seconds)

        if target_min <= cps <= target_max:
            return 1.0
        if cps < target_min:
            return max(0.0, 1 - ((target_min - cps) / target_min))
        return max(0.0, 1 - ((cps - target_max) / max(target_max, 1.0)))

    @staticmethod
    def _feedback_for_japanese(overlap: float, pace_score: float, pause_ratio: float) -> list[str]:
        feedback: list[str] = []
        if overlap < 0.7:
            feedback.append("Repite la frase por bloques cortos y confirma cada mora.")
        if pace_score < 0.7:
            feedback.append("Ajusta el ritmo para imitar el audio objetivo, sin acelerar al final.")
        if pause_ratio > 0.25:
            feedback.append("Reduce pausas largas y conecta mejor las palabras funcionales.")
        if not feedback:
            feedback.append("Buen shadowing. Mantén el mismo ritmo y claridad en la siguiente frase.")
        return feedback
