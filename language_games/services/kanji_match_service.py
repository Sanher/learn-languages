from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import logging
import re
import unicodedata

from .game_service import GameActivity
from .writing_support import writing_support_profile

GAME_TYPE_KANJI_MATCH = "kanji_match"
LANGUAGE_JAPANESE = "ja"
# Service traces to monitor flow and results in HA.
logger = logging.getLogger("learn_languages.games.kanji_match")

# This game is reserved for languages that do not use a western alphabet.
WESTERN_ALPHABET_LANGUAGE_CODES = {
    "en",
    "es",
    "fr",
    "de",
    "it",
    "pt",
    "ca",
    "nl",
}


@dataclass(frozen=True)
class KanjiPair:
    symbol: str
    meaning: str
    reading_romaji: str


JAPANESE_KANJI_PAIRS_BY_LEVEL: dict[int, list[KanjiPair]] = {
    1: [
        KanjiPair("日", "day/sun", "nichi / hi"),
        KanjiPair("月", "month/moon", "getsu / tsuki"),
        KanjiPair("水", "water", "sui / mizu"),
        KanjiPair("火", "fire", "ka / hi"),
        KanjiPair("木", "tree", "moku / ki"),
        KanjiPair("山", "mountain", "san / yama"),
    ],
    2: [
        KanjiPair("学", "study", "gaku / mana"),
        KanjiPair("校", "school", "kou"),
        KanjiPair("先", "previous", "sen / saki"),
        KanjiPair("生", "life/birth", "sei / ikiru"),
        KanjiPair("電", "electricity", "den"),
        KanjiPair("車", "car", "sha / kuruma"),
    ],
    3: [
        KanjiPair("働", "work", "dou / hataraku"),
        KanjiPair("験", "experience/exam", "ken"),
        KanjiPair("説", "explain/opinion", "setsu / toku"),
        KanjiPair("続", "continue", "zoku / tsudzuku"),
        KanjiPair("準", "prepare/standard", "jun"),
        KanjiPair("環", "ring/environment", "kan"),
    ],
}


@dataclass(frozen=True)
class KanjiMatchAttempt:
    language: str
    expected_pairs: list[KanjiPair]
    learner_readings: dict[str, str] = field(default_factory=dict)
    learner_meanings: dict[str, str] = field(default_factory=dict)
    learner_matches: dict[str, str] = field(default_factory=dict)
    level: int = 1


class KanjiMatchService:
    """Reusable kanji match service for non-western languages (initial Japanese implementation)."""

    game_type = GAME_TYPE_KANJI_MATCH

    def is_language_eligible(self, language: str) -> bool:
        return language not in WESTERN_ALPHABET_LANGUAGE_CODES

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        if not self.is_language_eligible(language):
            logger.info("activities_skipped western_language=%s", language)
            return []
        if language != LANGUAGE_JAPANESE:
            logger.info("activities_skipped unsupported_language=%s", language)
            return []
        support = writing_support_profile(level)
        activities = self._activities_for_japanese(level=level, support=support)
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def build_attempt_view(
        self,
        language: str,
        level: int = 1,
        show_translation: bool = False,
        hide_translation_hint: bool = False,
    ) -> dict:
        pairs = self.get_pairs(language=language, level=level)
        support = writing_support_profile(level)
        return self._view_payload(
            pairs=pairs,
            support=support,
            show_translation=show_translation,
            hide_translation_hint=hide_translation_hint,
        )

    def get_pairs(self, language: str, level: int = 1) -> list[KanjiPair]:
        if language != LANGUAGE_JAPANESE:
            logger.info("pairs_skipped unsupported_language=%s", language)
            return []
        max_level = max(JAPANESE_KANJI_PAIRS_BY_LEVEL.keys())
        selected_level = min(max(1, level), max_level)
        pairs = JAPANESE_KANJI_PAIRS_BY_LEVEL[selected_level]
        logger.debug("pairs_ready language=%s requested_level=%s normalized_level=%s count=%s", language, level, selected_level, len(pairs))
        return pairs

    def evaluate_attempt(self, attempt: KanjiMatchAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s expected_pairs=%s learner_readings=%s learner_meanings=%s",
            attempt.language,
            attempt.level,
            len(attempt.expected_pairs),
            len(attempt.learner_readings),
            len(attempt.learner_meanings or attempt.learner_matches),
        )
        if not self.is_language_eligible(attempt.language):
            logger.warning("evaluate_invalid western_language=%s", attempt.language)
            raise ValueError(f"kanji_match does not apply to western-alphabet languages: {attempt.language}")
        if attempt.language != LANGUAGE_JAPANESE:
            logger.warning("evaluate_invalid unsupported_language=%s", attempt.language)
            raise ValueError(f"Unsupported language in kanji_match: {attempt.language}")

        expected_meanings = {pair.symbol: pair.meaning for pair in attempt.expected_pairs}
        expected_readings = {pair.symbol: pair.reading_romaji for pair in attempt.expected_pairs}
        total = len(expected_meanings)
        if total == 0:
            logger.warning("evaluate_empty_expected language=%s level=%s", attempt.language, attempt.level)
            return {
                "game_type": self.game_type,
                "language": attempt.language,
                "score": 0,
                "accuracy": 0.0,
                "mistakes": [],
            }

        support = writing_support_profile(attempt.level)
        require_meaning_input = bool(attempt.level >= 2)
        provided_readings = {symbol: (attempt.learner_readings.get(symbol, "") or "").strip() for symbol in expected_readings}
        provided_meanings = attempt.learner_meanings or attempt.learner_matches
        # Compatibility: if legacy payload arrives without readings, keep exact-meaning evaluation mode.
        has_reading_answers = any(value for value in provided_readings.values())
        if not has_reading_answers:
            return self._evaluate_legacy_meaning_mode(
                attempt=attempt,
                expected_meanings=expected_meanings,
                support=support,
            )

        reading_hits = 0
        meaning_points = 0.0
        mistakes: list[dict[str, str]] = []
        reading_results: list[dict[str, str | bool]] = []
        meaning_results: list[dict[str, str]] = []

        for symbol, expected_reading in expected_readings.items():
            learner_reading = provided_readings.get(symbol, "")
            reading_ok = self._normalize_text(learner_reading) == self._normalize_text(expected_reading)
            if reading_ok:
                reading_hits += 1
            else:
                mistakes.append(
                    {
                        "symbol": symbol,
                        "type": "reading",
                        "expected_reading": expected_reading,
                        "learner_reading": learner_reading,
                    }
                )
            reading_results.append(
                {
                    "symbol": symbol,
                    "expected_reading": expected_reading,
                    "learner_reading": learner_reading,
                    "is_correct": reading_ok,
                }
            )

            if not require_meaning_input:
                continue

            expected_meaning = expected_meanings[symbol]
            learner_meaning = (provided_meanings.get(symbol, "") or "").strip()
            meaning_status = self._meaning_status(learner_meaning=learner_meaning, expected_meaning=expected_meaning)
            meaning_results.append(
                {
                    "symbol": symbol,
                    "expected_meaning": expected_meaning,
                    "learner_meaning": learner_meaning,
                    "status": meaning_status,
                }
            )
            if meaning_status == "correct":
                meaning_points += 1.0
            elif meaning_status == "almost_correct":
                meaning_points += 0.5
                mistakes.append(
                    {
                        "symbol": symbol,
                        "type": "meaning_almost",
                        "expected_meaning": expected_meaning,
                        "learner_meaning": learner_meaning,
                    }
                )
            else:
                mistakes.append(
                    {
                        "symbol": symbol,
                        "type": "meaning",
                        "expected_meaning": expected_meaning,
                        "learner_meaning": learner_meaning,
                    }
                )

        reading_accuracy = reading_hits / total
        meaning_accuracy = (meaning_points / total) if require_meaning_input else None
        combined_accuracy = (
            ((reading_accuracy * 0.5) + (meaning_accuracy * 0.5))
            if require_meaning_input and meaning_accuracy is not None
            else reading_accuracy
        )
        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "score": round(combined_accuracy * 100),
            "accuracy": round(combined_accuracy, 2),
            "reading_accuracy": round(reading_accuracy, 2),
            "require_meaning_input": require_meaning_input,
            "reading_results": reading_results,
            "meaning_results": meaning_results,
            "mistakes": mistakes,
            "display": self._view_payload(
                pairs=attempt.expected_pairs,
                support=support,
                show_translation=True,
            ),
            "retry_state": self._view_payload(
                pairs=attempt.expected_pairs,
                support=support,
                show_translation=False,
                hide_translation_hint=True,
            ),
        }
        if meaning_accuracy is not None:
            result["meaning_accuracy"] = round(meaning_accuracy, 2)
        logger.info(
            "evaluate_done language=%s level=%s score=%s reading_accuracy=%.2f meaning_accuracy=%s mistakes=%s",
            attempt.language,
            attempt.level,
            result["score"],
            reading_accuracy,
            None if meaning_accuracy is None else round(meaning_accuracy, 2),
            len(mistakes),
        )
        return result

    def _evaluate_legacy_meaning_mode(
        self,
        attempt: KanjiMatchAttempt,
        expected_meanings: dict[str, str],
        support,
    ) -> dict:
        hits = 0
        mistakes: list[dict[str, str]] = []
        for symbol, expected_meaning in expected_meanings.items():
            learner_meaning = attempt.learner_matches.get(symbol, "")
            if learner_meaning == expected_meaning:
                hits += 1
                continue
            mistakes.append(
                {
                    "symbol": symbol,
                    "type": "legacy_meaning",
                    "expected_meaning": expected_meaning,
                    "learner_meaning": learner_meaning,
                }
            )

        total = len(expected_meanings)
        accuracy = (hits / total) if total > 0 else 0.0
        return {
            "game_type": self.game_type,
            "language": attempt.language,
            "score": round(accuracy * 100),
            "accuracy": round(accuracy, 2),
            "reading_accuracy": round(accuracy, 2),
            "require_meaning_input": False,
            "reading_results": [],
            "meaning_results": [],
            "mistakes": mistakes,
            "display": self._view_payload(
                pairs=attempt.expected_pairs,
                support=support,
                show_translation=True,
            ),
            "retry_state": self._view_payload(
                pairs=attempt.expected_pairs,
                support=support,
                show_translation=False,
                hide_translation_hint=True,
            ),
        }

    def _activities_for_japanese(self, level: int, support) -> list[GameActivity]:
        pairs = self.get_pairs(language=LANGUAGE_JAPANESE, level=level)
        chunks = [pairs[i : i + 4] for i in range(0, len(pairs), 4)]

        activities: list[GameActivity] = []
        for idx, group in enumerate(chunks, start=1):
            symbols = ", ".join(pair.symbol for pair in group)
            readings = ", ".join(f"{pair.symbol}:{pair.reading_romaji}" for pair in group)
            meanings = ", ".join(pair.meaning for pair in group)

            lines = [f"Match kanji: {symbols}"]
            if support.show_romanized_line:
                lines.append(f"Readings (romaji): {readings}")
            if support.show_options:
                lines.append(f"Meaning bank: {meanings}")
            else:
                lines.append("Write the meaning for each kanji.")
            if support.show_translation_hint and group:
                lines.append(f"Translation hint: {group[0].symbol} = {group[0].meaning}")

            activities.append(
                GameActivity(
                    activity_id=f"ja-kanji-match-{level}-{idx}",
                    language=LANGUAGE_JAPANESE,
                    game_type=self.game_type,
                    prompt="\n".join(lines),
                    level=level,
                )
            )
        return activities

    @staticmethod
    def _view_payload(
        pairs: list[KanjiPair],
        support,
        show_translation: bool,
        hide_translation_hint: bool = False,
    ) -> dict:
        translation_map = {pair.symbol: pair.meaning for pair in pairs}
        reading_map = {pair.symbol: pair.reading_romaji for pair in pairs}
        show_translation_hint = bool(support.show_translation_hint and not hide_translation_hint)
        return {
            "assistance_stage": support.stage,
            "show_kanji_line": True,
            "kanji_symbols": [pair.symbol for pair in pairs],
            "show_romanized_line": bool(support.show_romanized_line),
            "reading_romaji": reading_map if support.show_romanized_line else {},
            "show_options": bool(support.show_options),
            "options": list(translation_map.values()) if support.show_options else [],
            "show_translation_hint": show_translation_hint,
            "translation_hint": translation_map if show_translation_hint else {},
            "show_literal_translation": show_translation,
            "literal_translation": translation_map if show_translation else {},
            "retry_available": True,
            "require_meaning_input": support.stage in {"intermediate", "advanced"},
        }

    @staticmethod
    def _meaning_status(learner_meaning: str, expected_meaning: str) -> str:
        learner = KanjiMatchService._normalize_text(learner_meaning)
        if not learner:
            return "incorrect"

        candidates = [
            KanjiMatchService._normalize_text(part)
            for part in re.split(r"[/,;]", expected_meaning)
            if part.strip()
        ]
        if not candidates:
            return "incorrect"
        if learner in candidates:
            return "correct"

        best_ratio = max(SequenceMatcher(a=learner, b=candidate).ratio() for candidate in candidates)
        learner_tokens = set(learner.split())
        best_overlap = 0.0
        if learner_tokens:
            for candidate in candidates:
                candidate_tokens = set(candidate.split())
                if not candidate_tokens:
                    continue
                overlap = len(learner_tokens & candidate_tokens) / len(candidate_tokens)
                best_overlap = max(best_overlap, overlap)

        if best_ratio >= 0.74 or best_overlap >= 0.5:
            return "almost_correct"
        return "incorrect"

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = unicodedata.normalize("NFKD", value or "")
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()
