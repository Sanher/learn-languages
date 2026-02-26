from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import re

from .game_service import GameActivity

GAME_TYPE_MORA_ROMANIZATION = "mora_romanization"
LANGUAGE_JAPANESE = "ja"
logger = logging.getLogger("learn_languages.games.mora_romanization")


@dataclass(frozen=True)
class MoraRomanizationItem:
    item_id: str
    language: str
    mora_kana: list[str]
    mora_romaji: list[str]
    expected_words: list[str]
    japanese_text: str
    kanji_mora_tokens: list[str]
    literal_translation: str
    level: int


@dataclass(frozen=True)
class MoraRomanizationAttempt:
    language: str
    item_id: str
    user_romanized_text: str
    level: int = 1


JAPANESE_MORA_ROMANIZATION_ITEMS_BY_LEVEL: dict[int, list[MoraRomanizationItem]] = {
    1: [
        MoraRomanizationItem(
            item_id="ja-mora-romanization-1-1",
            language="ja",
            mora_kana=["わ", "た", "し", "は", "が", "く", "せ", "い", "で", "す"],
            mora_romaji=["wa", "ta", "shi", "wa", "ga", "ku", "se", "i", "de", "su"],
            expected_words=["watashi", "wa", "gakusei", "desu"],
            japanese_text="わたしはがくせいです",
            kanji_mora_tokens=["私(わ)", "た", "し", "は", "学(が)", "く", "生(せ)", "い", "で", "す"],
            literal_translation="I topic student am",
            level=1,
        ),
        MoraRomanizationItem(
            item_id="ja-mora-romanization-1-2",
            language="ja",
            mora_kana=["こ", "れ", "は", "ほ", "ん", "で", "す"],
            mora_romaji=["ko", "re", "wa", "ho", "n", "de", "su"],
            expected_words=["kore", "wa", "hon", "desu"],
            japanese_text="これはほんです",
            kanji_mora_tokens=["こ", "れ", "は", "本(ほ)", "ん", "で", "す"],
            literal_translation="this topic book is",
            level=1,
        ),
    ],
    2: [
        MoraRomanizationItem(
            item_id="ja-mora-romanization-2-1",
            language="ja",
            mora_kana=["きょ", "う", "は", "す", "し", "を", "た", "べ", "ま", "す"],
            mora_romaji=["kyo", "u", "wa", "su", "shi", "o", "ta", "be", "ma", "su"],
            expected_words=["kyou", "wa", "sushi", "o", "tabemasu"],
            japanese_text="きょうはすしをたべます",
            kanji_mora_tokens=["今(きょ)", "日(う)", "は", "寿(す)", "司(し)", "を", "食(た)", "べ", "ま", "す"],
            literal_translation="today topic sushi object eat",
            level=2,
        )
    ],
    3: [
        MoraRomanizationItem(
            item_id="ja-mora-romanization-3-1",
            language="ja",
            mora_kana=["あ", "し", "た", "と", "も", "だ", "ち", "と", "え", "い", "が", "を", "み", "ま", "す"],
            mora_romaji=["a", "shi", "ta", "to", "mo", "da", "chi", "to", "e", "i", "ga", "o", "mi", "ma", "su"],
            expected_words=["ashita", "tomodachi", "to", "eiga", "o", "mimasu"],
            japanese_text="あしたともだちとえいがをみます",
            kanji_mora_tokens=["明(あ)", "日(し)", "た", "友(と)", "達(も)", "だ", "ち", "と", "映(え)", "画(い)", "が", "を", "見(み)", "ま", "す"],
            literal_translation="tomorrow friend with movie object watch",
            level=3,
        )
    ],
}


class MoraRomanizationService:
    """Romanization segmentation game with mora support by level."""

    game_type = GAME_TYPE_MORA_ROMANIZATION

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        items = self.get_items(language=language, level=level)
        if not items:
            return []

        # Beginner shows mora-by-mora scaffolding; advanced removes that help.
        beginner_mode = level <= 1
        activities: list[GameActivity] = []
        for item in items:
            lines = ["Romanize and group mora into western words."]
            if beginner_mode:
                lines.append(f"Mora (kana): {' | '.join(item.mora_kana)}")
                lines.append(f"Mora (romaji): {' '.join(item.mora_romaji)}")
            else:
                lines.append(f"Japanese text: {item.japanese_text}")
            lines.append("Write your answer using spaces between words.")
            activities.append(
                GameActivity(
                    activity_id=item.item_id,
                    language=language,
                    game_type=self.game_type,
                    prompt="\n".join(lines),
                    level=item.level,
                )
            )
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def get_items(self, language: str, level: int = 1) -> list[MoraRomanizationItem]:
        if language != LANGUAGE_JAPANESE:
            logger.info("items_skipped unsupported_language=%s", language)
            return []
        min_level = min(JAPANESE_MORA_ROMANIZATION_ITEMS_BY_LEVEL)
        max_level = max(JAPANESE_MORA_ROMANIZATION_ITEMS_BY_LEVEL)
        normalized_level = min(max(min_level, level), max_level)
        items = JAPANESE_MORA_ROMANIZATION_ITEMS_BY_LEVEL[normalized_level]
        logger.debug(
            "items_ready language=%s requested_level=%s normalized_level=%s count=%s",
            language,
            level,
            normalized_level,
            len(items),
        )
        return items

    def evaluate_attempt(self, attempt: MoraRomanizationAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s item_id=%s user_len=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            len(attempt.user_romanized_text or ""),
        )
        item = self._find_item(language=attempt.language, item_id=attempt.item_id, level=attempt.level)
        expected_words = [self._normalize_word(token) for token in item.expected_words]
        user_words = self._tokenize_user_words(attempt.user_romanized_text)

        expected_joined = "".join(expected_words)
        user_joined = "".join(user_words)
        romanization_accuracy = SequenceMatcher(None, expected_joined, user_joined).ratio() if expected_joined else 0.0
        segmentation_accuracy = self._segmentation_accuracy(expected_words, user_words)
        is_correct = user_words == expected_words
        # Accuracy combines content similarity and correct word boundaries.
        score = 100 if is_correct else round(((romanization_accuracy * 0.6) + (segmentation_accuracy * 0.4)) * 100)
        # In advanced levels, reveal kanji mora line only for correct answers.
        show_kanji = attempt.level <= 1 or is_correct
        feedback = self._feedback(
            is_correct=is_correct,
            romanization_accuracy=romanization_accuracy,
            segmentation_accuracy=segmentation_accuracy,
        )

        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "item_id": attempt.item_id,
            "is_correct": is_correct,
            "score": max(0, min(100, score)),
            "romanization_accuracy": round(romanization_accuracy, 2),
            "segmentation_accuracy": round(segmentation_accuracy, 2),
            "expected_words": expected_words,
            "user_words": user_words,
            "feedback": feedback,
            "literal_translation": item.literal_translation,
            "show_kanji_mora_line": show_kanji,
            "kanji_mora_line": " | ".join(item.kanji_mora_tokens) if show_kanji else None,
            "retry_available": True,
            "display": {
                "show_kanji_mora_line": show_kanji,
                "kanji_mora_line": " | ".join(item.kanji_mora_tokens) if show_kanji else None,
            },
            "retry_state": {
                "show_kanji_mora_line": False,
                "kanji_mora_line": None,
            },
        }
        logger.info(
            "evaluate_done language=%s level=%s item_id=%s score=%s is_correct=%s show_kanji=%s romanization_accuracy=%.2f segmentation_accuracy=%.2f",
            attempt.language,
            attempt.level,
            attempt.item_id,
            result["score"],
            is_correct,
            show_kanji,
            romanization_accuracy,
            segmentation_accuracy,
        )
        return result

    def _find_item(self, language: str, item_id: str, level: int) -> MoraRomanizationItem:
        for item in self.get_items(language=language, level=level):
            if item.item_id == item_id:
                return item
        logger.warning("item_not_found language=%s level=%s item_id=%s", language, level, item_id)
        raise ValueError(f"item_id not found for language={language}, level={level}: {item_id}")

    @staticmethod
    def _normalize_word(token: str) -> str:
        return re.sub(r"[^a-z]", "", (token or "").strip().lower())

    @classmethod
    def _tokenize_user_words(cls, text: str) -> list[str]:
        raw_tokens = re.split(r"\s+", (text or "").strip())
        return [cls._normalize_word(token) for token in raw_tokens if cls._normalize_word(token)]

    @staticmethod
    def _boundary_positions(words: list[str]) -> set[int]:
        boundaries: set[int] = set()
        cursor = 0
        for word in words[:-1]:
            cursor += len(word)
            boundaries.add(cursor)
        return boundaries

    @classmethod
    def _segmentation_accuracy(cls, expected_words: list[str], user_words: list[str]) -> float:
        expected_boundaries = cls._boundary_positions(expected_words)
        user_boundaries = cls._boundary_positions(user_words)
        if not expected_boundaries:
            return 1.0 if not user_boundaries else 0.0
        hits = len(expected_boundaries.intersection(user_boundaries))
        return hits / len(expected_boundaries)

    @staticmethod
    def _feedback(is_correct: bool, romanization_accuracy: float, segmentation_accuracy: float) -> str:
        if is_correct:
            return "Great job. Romanization and word grouping are correct."
        if romanization_accuracy >= 0.9 and segmentation_accuracy < 1.0:
            return "Romanization is close, but word boundaries are still incorrect."
        if romanization_accuracy < 0.65:
            return "Romanization differs from the expected mora sequence."
        return "Good attempt. Review mora grouping and try again."
