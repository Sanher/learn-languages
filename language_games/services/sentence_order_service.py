from __future__ import annotations

from dataclasses import dataclass
import logging
from random import Random

from .game_service import GameActivity
from .writing_support import EASTERN_SCRIPT_LANGUAGE_CODES, is_eastern_script, writing_support_profile

GAME_TYPE_SENTENCE_ORDER = "sentence_order"
# Service traces to monitor flow and results in HA.
logger = logging.getLogger("learn_languages.games.sentence_order")


@dataclass(frozen=True)
class SentenceOrderItem:
    item_id: str
    language: str
    ordered_tokens: list[str]
    script_line: str
    romanized_line: str | None
    literal_translation: str
    level: int


@dataclass(frozen=True)
class SentenceOrderAttempt:
    language: str
    item_id: str
    ordered_tokens_by_user: list[str]
    level: int = 1


JAPANESE_SENTENCE_ORDER_ITEMS_BY_LEVEL: dict[int, list[SentenceOrderItem]] = {
    1: [
        SentenceOrderItem(
            item_id="ja-sentence-order-1-1",
            language="ja",
            ordered_tokens=["わたし", "は", "がくせい", "です"],
            script_line="私は学生です。",
            romanized_line="watashi wa gakusei desu",
            literal_translation="I topic student am",
            level=1,
        ),
        SentenceOrderItem(
            item_id="ja-sentence-order-1-2",
            language="ja",
            ordered_tokens=["これ", "は", "ほん", "です"],
            script_line="これは本です。",
            romanized_line="kore wa hon desu",
            literal_translation="this topic book is",
            level=1,
        ),
    ],
    2: [
        SentenceOrderItem(
            item_id="ja-sentence-order-2-1",
            language="ja",
            ordered_tokens=["きょう", "は", "しごと", "が", "あります"],
            script_line="今日は仕事があります。",
            romanized_line="kyou wa shigoto ga arimasu",
            literal_translation="today topic work subject exists",
            level=2,
        ),
        SentenceOrderItem(
            item_id="ja-sentence-order-2-2",
            language="ja",
            ordered_tokens=["わたし", "は", "えき", "に", "いきます"],
            script_line="私は駅に行きます。",
            romanized_line="watashi wa eki ni ikimasu",
            literal_translation="I topic station to go",
            level=2,
        ),
    ],
    3: [
        SentenceOrderItem(
            item_id="ja-sentence-order-3-1",
            language="ja",
            ordered_tokens=["あした", "ともだち", "と", "えいが", "を", "みます"],
            script_line="明日友達と映画を見ます。",
            romanized_line="ashita tomodachi to eiga o mimasu",
            literal_translation="tomorrow friend with movie object watch",
            level=3,
        ),
    ],
}

ENGLISH_SENTENCE_ORDER_ITEMS_BY_LEVEL: dict[int, list[SentenceOrderItem]] = {
    1: [
        SentenceOrderItem(
            item_id="en-sentence-order-1-1",
            language="en",
            ordered_tokens=["I", "study", "every", "day"],
            script_line="I study every day.",
            romanized_line=None,
            literal_translation="I study every day",
            level=1,
        ),
        SentenceOrderItem(
            item_id="en-sentence-order-1-2",
            language="en",
            ordered_tokens=["This", "is", "my", "book"],
            script_line="This is my book.",
            romanized_line=None,
            literal_translation="this is my book",
            level=1,
        ),
    ],
}


class SentenceOrderService:
    """Reusable sentence-order service (Japanese and western-alphabet languages)."""

    game_type = GAME_TYPE_SENTENCE_ORDER

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        items = self.get_items(language=language, level=level)
        support = writing_support_profile(level)
        activities: list[GameActivity] = []

        for item in items:
            scrambled = self._scrambled_tokens(item)
            header = f"Order tokens: {' | '.join(scrambled)}"
            if self._is_eastern_script(language):
                lines = [header, f"Script: {item.script_line}"]
                if support.show_romanized_line and item.romanized_line:
                    lines.append(f"Romanized: {item.romanized_line}")
                if support.show_translation_hint:
                    lines.append(f"Translation hint: {item.literal_translation}")
                prompt = "\n".join(lines)
            else:
                lines = [header, f"Base sentence: {item.script_line}"]
                if support.show_translation_hint:
                    lines.append(f"Translation hint: {item.literal_translation}")
                prompt = "\n".join(lines)

            activities.append(
                GameActivity(
                    activity_id=item.item_id,
                    language=language,
                    game_type=self.game_type,
                    prompt=prompt,
                    level=item.level,
                )
            )

        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def get_items(self, language: str, level: int = 1) -> list[SentenceOrderItem]:
        all_by_level = self._items_by_level_for_language(language)
        if not all_by_level:
            logger.info("items_skipped unsupported_language=%s", language)
            return []

        min_level = min(all_by_level.keys())
        max_level = max(all_by_level.keys())
        normalized_level = min(max(min_level, level), max_level)
        items = all_by_level[normalized_level]
        logger.debug("items_ready language=%s requested_level=%s normalized_level=%s count=%s", language, level, normalized_level, len(items))
        return items

    def build_attempt_view(
        self,
        language: str,
        item_id: str,
        level: int = 1,
        show_translation: bool = False,
        hide_translation_hint: bool = False,
    ) -> dict:
        item = self._find_item(language=language, item_id=item_id, level=level)
        support = writing_support_profile(level)
        return self._view_payload(
            item=item,
            support=support,
            show_translation=show_translation,
            hide_translation_hint=hide_translation_hint,
        )

    def evaluate_attempt(self, attempt: SentenceOrderAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s item_id=%s tokens_count=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            len(attempt.ordered_tokens_by_user),
        )
        item = self._find_item(language=attempt.language, item_id=attempt.item_id, level=attempt.level)
        support = writing_support_profile(attempt.level)
        is_correct = attempt.ordered_tokens_by_user == item.ordered_tokens
        accuracy = self._position_accuracy(item.ordered_tokens, attempt.ordered_tokens_by_user)

        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "item_id": attempt.item_id,
            "is_correct": is_correct,
            "score": round(accuracy * 100),
            "user_sentence": " ".join(attempt.ordered_tokens_by_user),
            "expected_sentence": " ".join(item.ordered_tokens),
            "feedback": (
                "Correct order. Well done."
                if is_correct
                else "Order is not correct yet. Review particles and verb position."
            ),
            "display": self._view_payload(item=item, support=support, show_translation=True),
            "retry_state": self._view_payload(
                item=item,
                support=support,
                show_translation=False,
                hide_translation_hint=True,
            ),
        }
        logger.info(
            "evaluate_done language=%s level=%s item_id=%s is_correct=%s score=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            is_correct,
            result["score"],
        )
        return result

    def _find_item(self, language: str, item_id: str, level: int) -> SentenceOrderItem:
        items = self.get_items(language=language, level=level)
        for item in items:
            if item.item_id == item_id:
                return item
        logger.warning("item_not_found language=%s level=%s item_id=%s", language, level, item_id)
        raise ValueError(f"item_id not found for language={language}, level={level}: {item_id}")

    def _view_payload(
        self,
        item: SentenceOrderItem,
        support,
        show_translation: bool,
        hide_translation_hint: bool = False,
    ) -> dict:
        show_romanized = bool(support.show_romanized_line and item.romanized_line)
        show_translation_hint = bool(support.show_translation_hint and not hide_translation_hint)
        payload = {
            "show_kanji_line": self._is_eastern_script(item.language),
            "kanji_line": item.script_line if self._is_eastern_script(item.language) else None,
            "assistance_stage": support.stage,
            "show_romanized_line": show_romanized,
            "romanized_line": item.romanized_line if show_romanized else None,
            "base_line": item.script_line if not self._is_eastern_script(item.language) else None,
            "show_translation_hint": show_translation_hint,
            "translation_hint": item.literal_translation if show_translation_hint else None,
            "show_literal_translation": show_translation,
            "literal_translation": item.literal_translation if show_translation else None,
            "retry_available": True,
        }
        return payload

    @staticmethod
    def _position_accuracy(expected: list[str], observed: list[str]) -> float:
        if not expected:
            return 0.0
        comparisons = min(len(expected), len(observed))
        if comparisons == 0:
            return 0.0
        hits = sum(1 for index in range(comparisons) if expected[index] == observed[index])
        return hits / len(expected)

    @staticmethod
    def _is_eastern_script(language: str) -> bool:
        return is_eastern_script(language)

    @staticmethod
    def _items_by_level_for_language(language: str) -> dict[int, list[SentenceOrderItem]]:
        if language == "ja":
            return JAPANESE_SENTENCE_ORDER_ITEMS_BY_LEVEL
        if language == "en":
            return ENGLISH_SENTENCE_ORDER_ITEMS_BY_LEVEL
        return {}

    @staticmethod
    def _scrambled_tokens(item: SentenceOrderItem) -> list[str]:
        tokens = item.ordered_tokens.copy()
        rnd = Random(item.item_id)
        rnd.shuffle(tokens)
        if tokens == item.ordered_tokens and len(tokens) > 1:
            tokens[0], tokens[1] = tokens[1], tokens[0]
        return tokens
