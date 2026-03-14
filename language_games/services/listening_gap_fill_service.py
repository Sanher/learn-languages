from __future__ import annotations

from dataclasses import dataclass
import logging

from .game_service import GameActivity
from .writing_support import EASTERN_SCRIPT_LANGUAGE_CODES, is_eastern_script, writing_support_profile

GAME_TYPE_LISTENING_GAP_FILL = "listening_gap_fill"
# Service traces to monitor flow and results in HA.
logger = logging.getLogger("learn_languages.games.listening_gap_fill")


@dataclass(frozen=True)
class ListeningGapFillItem:
    item_id: str
    language: str
    tokens: list[str]
    gap_positions: list[int]
    options: list[str]
    script_line: str
    romanized_line: str | None
    literal_translation: str
    level: int


@dataclass(frozen=True)
class ListeningGapFillAttempt:
    language: str
    item_id: str
    user_gap_tokens: list[str]
    level: int = 1


JAPANESE_LISTENING_GAP_FILL_ITEMS_BY_LEVEL: dict[int, list[ListeningGapFillItem]] = {
    1: [
        ListeningGapFillItem(
            item_id="ja-gap-1-1",
            language="ja",
            tokens=["わたし", "は", "がくせい", "です"],
            gap_positions=[2],
            options=["がくせい", "せんせい", "いしゃ"],
            script_line="私は学生です。",
            romanized_line="watashi wa gakusei desu",
            literal_translation="I topic student am",
            level=1,
        ),
        ListeningGapFillItem(
            item_id="ja-gap-1-2",
            language="ja",
            tokens=["これ", "は", "ほん", "です"],
            gap_positions=[2],
            options=["ほん", "つくえ", "くるま"],
            script_line="これは本です。",
            romanized_line="kore wa hon desu",
            literal_translation="this topic book is",
            level=1,
        ),
    ],
    2: [
        ListeningGapFillItem(
            item_id="ja-gap-2-1",
            language="ja",
            tokens=["きょう", "は", "すし", "を", "たべます"],
            gap_positions=[2],
            options=["すし", "てんぷら", "うどん"],
            script_line="今日は寿司を食べます。",
            romanized_line="kyou wa sushi o tabemasu",
            literal_translation="today topic sushi object eat",
            level=2,
        ),
        ListeningGapFillItem(
            item_id="ja-gap-2-2",
            language="ja",
            tokens=["えき", "に", "いきます"],
            gap_positions=[0],
            options=["えき", "うち", "みせ"],
            script_line="駅に行きます。",
            romanized_line="eki ni ikimasu",
            literal_translation="station to go",
            level=2,
        ),
    ],
    3: [
        ListeningGapFillItem(
            item_id="ja-gap-3-1",
            language="ja",
            tokens=["あした", "ともだち", "と", "えいが", "を", "みます"],
            gap_positions=[3],
            options=["えいが", "ほん", "おんがく"],
            script_line="明日友達と映画を見ます。",
            romanized_line="ashita tomodachi to eiga o mimasu",
            literal_translation="tomorrow friend with movie object watch",
            level=3,
        ),
    ],
}

ENGLISH_LISTENING_GAP_FILL_ITEMS_BY_LEVEL: dict[int, list[ListeningGapFillItem]] = {
    1: [
        ListeningGapFillItem(
            item_id="en-gap-1-1",
            language="en",
            tokens=["I", "study", "every", "day"],
            gap_positions=[1],
            options=["study", "eat", "walk"],
            script_line="I study every day.",
            romanized_line=None,
            literal_translation="I study every day",
            level=1,
        )
    ],
    2: [
        ListeningGapFillItem(
            item_id="en-gap-2-1",
            language="en",
            tokens=["She", "goes", "to", "school"],
            gap_positions=[1],
            options=[],
            script_line="She goes to school.",
            romanized_line=None,
            literal_translation="she goes to school",
            level=2,
        )
    ],
    3: [
        ListeningGapFillItem(
            item_id="en-gap-3-1",
            language="en",
            tokens=["They", "usually", "watch", "movies", "on", "weekends"],
            gap_positions=[2],
            options=[],
            script_line="They usually watch movies on weekends.",
            romanized_line=None,
            literal_translation="they usually watch movies on weekends",
            level=3,
        )
    ],
}


class ListeningGapFillService:
    """Reusable listening gap-fill service with progressive support by level."""

    game_type = GAME_TYPE_LISTENING_GAP_FILL

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        items = self.get_items(language=language, level=level)
        support = writing_support_profile(level)

        activities: list[GameActivity] = []
        for item in items:
            template = self._template_with_gaps(item.tokens, item.gap_positions)
            options_line = f"Options: {', '.join(item.options)}" if support.show_options and item.options else ""

            prompt_lines = [f"Fill the gaps: {template}"]
            if self._is_eastern_script(language):
                prompt_lines.append(f"Script: {item.script_line}")
                if support.show_romanized_line and item.romanized_line:
                    prompt_lines.append(f"Romanized: {item.romanized_line}")
            else:
                prompt_lines.append(f"Base sentence: {item.script_line}")

            if support.show_translation_hint:
                prompt_lines.append(f"Translation hint: {item.literal_translation}")

            if options_line:
                prompt_lines.append(options_line)

            activities.append(
                GameActivity(
                    activity_id=item.item_id,
                    language=language,
                    game_type=self.game_type,
                    prompt="\n".join(prompt_lines),
                    level=item.level,
                )
            )
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    def get_items(self, language: str, level: int = 1) -> list[ListeningGapFillItem]:
        by_level = self._items_by_level_for_language(language)
        if not by_level:
            logger.info("items_skipped unsupported_language=%s", language)
            return []

        min_level = min(by_level.keys())
        max_level = max(by_level.keys())
        normalized_level = min(max(min_level, level), max_level)
        items = by_level[normalized_level]
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

    def evaluate_attempt(self, attempt: ListeningGapFillAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s item_id=%s gaps_submitted=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            len(attempt.user_gap_tokens),
        )
        item = self._find_item(language=attempt.language, item_id=attempt.item_id, level=attempt.level)
        support = writing_support_profile(attempt.level)

        expected = [item.tokens[position] for position in item.gap_positions]
        observed = attempt.user_gap_tokens[: len(expected)]
        accuracy = self._accuracy(expected, observed)
        is_correct = accuracy == 1.0

        user_sentence_tokens = item.tokens.copy()
        for idx, position in enumerate(item.gap_positions):
            replacement = attempt.user_gap_tokens[idx] if idx < len(attempt.user_gap_tokens) else "__"
            user_sentence_tokens[position] = replacement

        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "item_id": attempt.item_id,
            "is_correct": is_correct,
            "score": round(accuracy * 100),
            "expected_gap_tokens": expected,
            "user_gap_tokens": observed,
            "user_sentence": " ".join(user_sentence_tokens),
            "feedback": "Correct gap tokens." if is_correct else "Some gaps are incorrect. Listen again and retry.",
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

    def _find_item(self, language: str, item_id: str, level: int) -> ListeningGapFillItem:
        for item in self.get_items(language=language, level=level):
            if item.item_id == item_id:
                return item
        logger.warning("item_not_found language=%s level=%s item_id=%s", language, level, item_id)
        raise ValueError(f"item_id not found for language={language}, level={level}: {item_id}")

    def _view_payload(
        self,
        item: ListeningGapFillItem,
        support,
        show_translation: bool,
        hide_translation_hint: bool = False,
    ) -> dict:
        show_romanized = bool(support.show_romanized_line and item.romanized_line is not None)
        # Drag fragments should remain available in the UI even when written hints are reduced.
        show_options = bool(item.options)
        show_translation_hint = bool(support.show_translation_hint and not hide_translation_hint)
        return {
            "show_kanji_line": self._is_eastern_script(item.language),
            "kanji_line": item.script_line if self._is_eastern_script(item.language) else None,
            "base_line": item.script_line if not self._is_eastern_script(item.language) else None,
            "assistance_stage": support.stage,
            "show_romanized_line": show_romanized,
            "romanized_line": item.romanized_line if show_romanized else None,
            "show_options": show_options,
            "options": item.options if show_options else [],
            "show_translation_hint": show_translation_hint,
            "translation_hint": item.literal_translation if show_translation_hint else None,
            "show_literal_translation": show_translation,
            "literal_translation": item.literal_translation if show_translation else None,
            "retry_available": True,
        }

    @staticmethod
    def _template_with_gaps(tokens: list[str], gap_positions: list[int]) -> str:
        template_tokens = tokens.copy()
        for pos in gap_positions:
            if 0 <= pos < len(template_tokens):
                template_tokens[pos] = "__"
        return " ".join(template_tokens)

    @staticmethod
    def _accuracy(expected: list[str], observed: list[str]) -> float:
        if not expected:
            return 0.0
        hits = 0
        for idx, expected_token in enumerate(expected):
            observed_token = observed[idx] if idx < len(observed) else None
            if observed_token == expected_token:
                hits += 1
        return hits / len(expected)

    @staticmethod
    def _is_eastern_script(language: str) -> bool:
        return is_eastern_script(language)

    @staticmethod
    def _items_by_level_for_language(language: str) -> dict[int, list[ListeningGapFillItem]]:
        if language == "ja":
            return JAPANESE_LISTENING_GAP_FILL_ITEMS_BY_LEVEL
        if language == "en":
            return ENGLISH_LISTENING_GAP_FILL_ITEMS_BY_LEVEL
        return {}
