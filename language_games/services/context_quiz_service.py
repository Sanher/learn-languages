from __future__ import annotations

from dataclasses import dataclass
import logging

from .game_service import GameActivity
from .writing_support import EASTERN_SCRIPT_LANGUAGE_CODES, is_eastern_script, writing_support_profile

GAME_TYPE_CONTEXT_QUIZ = "context_quiz"
# Service traces to monitor flow and results in HA.
logger = logging.getLogger("learn_languages.games.context_quiz")


@dataclass(frozen=True)
class ContextQuizOption:
    option_id: str
    text: str
    is_correct: bool
    feedback: str
    romaji_text: str | None = None


@dataclass(frozen=True)
class ContextQuizItem:
    item_id: str
    language: str
    context_prompt: str
    script_line: str
    romanized_line: str | None
    literal_translation: str
    options: list[ContextQuizOption]
    level: int


@dataclass(frozen=True)
class ContextQuizAttempt:
    language: str
    item_id: str
    selected_option_id: str
    level: int = 1


JAPANESE_CONTEXT_QUIZ_ITEMS_BY_LEVEL: dict[int, list[ContextQuizItem]] = {
    1: [
        ContextQuizItem(
            item_id="ja-context-1-1",
            language="ja",
            context_prompt="You meet someone for the first time in a formal situation.",
            script_line="はじめまして。よろしくお願いします。",
            romanized_line="hajimemashite. yoroshiku onegaishimasu.",
            literal_translation="nice to meet you. please treat me favorably.",
            options=[
                ContextQuizOption(
                    "a",
                    "はじめまして。よろしくお願いします。",
                    True,
                    "Very appropriate for a formal first meeting.",
                    romaji_text="hajimemashite. yoroshiku onegaishimasu.",
                ),
                ContextQuizOption(
                    "b",
                    "おつかれさまです。",
                    False,
                    "This expression acknowledges effort, not self-introductions.",
                    romaji_text="otsukaresama desu.",
                ),
                ContextQuizOption(
                    "c",
                    "いただきます。",
                    False,
                    "Used before eating, not when introducing yourself.",
                    romaji_text="itadakimasu.",
                ),
            ],
            level=1,
        ),
        ContextQuizItem(
            item_id="ja-context-1-2",
            language="ja",
            context_prompt="You apologize for arriving late.",
            script_line="遅れてすみません。",
            romanized_line="okurete sumimasen.",
            literal_translation="sorry for being late.",
            options=[
                ContextQuizOption(
                    "a",
                    "いってきます。",
                    False,
                    "Used when leaving home.",
                    romaji_text="ittekimasu.",
                ),
                ContextQuizOption(
                    "b",
                    "遅れてすみません。",
                    True,
                    "Correct for apologizing about lateness.",
                    romaji_text="okurete sumimasen.",
                ),
                ContextQuizOption(
                    "c",
                    "おやすみなさい。",
                    False,
                    "Used when saying goodnight.",
                    romaji_text="oyasuminasai.",
                ),
            ],
            level=1,
        ),
    ],
    2: [
        ContextQuizItem(
            item_id="ja-context-2-1",
            language="ja",
            context_prompt="A client asks you to confirm a shipment in a formal email.",
            script_line="承知しました。確認してご連絡します。",
            romanized_line="shouchi shimashita. kakunin shite gorenraku shimasu.",
            literal_translation="understood. I will confirm and contact you.",
            options=[
                ContextQuizOption(
                    "a",
                    "わかった。あとでね。",
                    False,
                    "Too casual for a formal client context.",
                    romaji_text="wakatta. atode ne.",
                ),
                ContextQuizOption(
                    "b",
                    "承知しました。確認してご連絡します。",
                    True,
                    "Appropriate register for a client.",
                    romaji_text="shouchi shimashita. kakunin shite gorenraku shimasu.",
                ),
                ContextQuizOption(
                    "c",
                    "マジで？",
                    False,
                    "Too colloquial for a professional context.",
                    romaji_text="maji de?",
                ),
            ],
            level=2,
        )
    ],
    3: [
        ContextQuizItem(
            item_id="ja-context-3-1",
            language="ja",
            context_prompt="You need to decline a proposal respectfully in a corporate setting.",
            script_line="大変恐縮ですが、今回は見送らせていただきます。",
            romanized_line="taihen kyoushuku desu ga, konkai wa miokurasete itadakimasu.",
            literal_translation="we are very sorry, but we must decline this time.",
            options=[
                ContextQuizOption(
                    "a",
                    "それは無理です。",
                    False,
                    "Content is fine, but too direct.",
                    romaji_text="sore wa muri desu.",
                ),
                ContextQuizOption(
                    "b",
                    "大変恐縮ですが、今回は見送らせていただきます。",
                    True,
                    "Very appropriate in a formal register.",
                    romaji_text="taihen kyoushuku desu ga, konkai wa miokurasete itadakimasu.",
                ),
                ContextQuizOption(
                    "c",
                    "やだ。",
                    False,
                    "Inappropriate register.",
                    romaji_text="yada.",
                ),
            ],
            level=3,
        )
    ],
}

ENGLISH_CONTEXT_QUIZ_ITEMS_BY_LEVEL: dict[int, list[ContextQuizItem]] = {
    1: [
        ContextQuizItem(
            item_id="en-context-1-1",
            language="en",
            context_prompt="You are in a job interview and need a polite opening.",
            script_line="Thank you for taking the time to meet with me.",
            romanized_line=None,
            literal_translation="thank you for taking the time to meet with me",
            options=[
                ContextQuizOption("a", "Yo, what's up?", False, "Too informal for interview context."),
                ContextQuizOption("b", "Thank you for taking the time to meet with me.", True, "Appropriate formal tone."),
                ContextQuizOption("c", "Whatever works.", False, "Too casual and vague."),
            ],
            level=1,
        )
    ]
}


class ContextQuizService:
    """Reusable context quiz service with diagnostic purpose."""

    game_type = GAME_TYPE_CONTEXT_QUIZ

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        items = self.get_items(language=language, level=level)
        activities: list[GameActivity] = []

        for item in items:
            prompt_lines = [
                f"Context: {item.context_prompt}",
                "Choose the most appropriate expression.",
            ]

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

    @staticmethod
    def options_for_ui(options: list[ContextQuizOption]) -> list[dict[str, str]]:
        return [
            {
                "id": opt.option_id,
                "text": opt.text,
                "romaji": opt.romaji_text or "",
            }
            for opt in options
        ]

    def get_items(self, language: str, level: int = 1) -> list[ContextQuizItem]:
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

    def evaluate_attempt(self, attempt: ContextQuizAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s item_id=%s selected_option_id=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            attempt.selected_option_id,
        )
        item = self._find_item(language=attempt.language, item_id=attempt.item_id, level=attempt.level)
        support = writing_support_profile(attempt.level)
        option_map = {option.option_id: option for option in item.options}
        selected = option_map.get(attempt.selected_option_id)
        if selected is None:
            logger.warning(
                "evaluate_invalid_option language=%s level=%s item_id=%s selected_option_id=%s",
                attempt.language,
                attempt.level,
                attempt.item_id,
                attempt.selected_option_id,
            )
            raise ValueError(f"selected_option_id not found: {attempt.selected_option_id}")

        is_correct = selected.is_correct
        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "item_id": item.item_id,
            "selected_option_id": selected.option_id,
            "is_correct": is_correct,
            "score": 100 if is_correct else 0,
            "diagnostic_signal": "up" if is_correct else "review",
            "feedback": selected.feedback,
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

    def _find_item(self, language: str, item_id: str, level: int) -> ContextQuizItem:
        for item in self.get_items(language=language, level=level):
            if item.item_id == item_id:
                return item
        logger.warning("item_not_found language=%s level=%s item_id=%s", language, level, item_id)
        raise ValueError(f"item_id not found for language={language}, level={level}: {item_id}")

    def _view_payload(self, item: ContextQuizItem, support, show_translation: bool, hide_translation_hint: bool = False) -> dict:
        show_romanized = bool(support.show_romanized_line and item.romanized_line)
        show_translation_hint = bool(support.show_translation_hint and not hide_translation_hint)
        return {
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

    @staticmethod
    def _is_eastern_script(language: str) -> bool:
        return is_eastern_script(language)

    @staticmethod
    def _items_by_level_for_language(language: str) -> dict[int, list[ContextQuizItem]]:
        if language == "ja":
            return JAPANESE_CONTEXT_QUIZ_ITEMS_BY_LEVEL
        if language == "en":
            return ENGLISH_CONTEXT_QUIZ_ITEMS_BY_LEVEL
        return {}
