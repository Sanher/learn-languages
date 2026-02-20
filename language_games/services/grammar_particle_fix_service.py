from __future__ import annotations

from dataclasses import dataclass
import logging

from .game_service import GameActivity
from .writing_support import is_eastern_script, writing_support_profile

GAME_TYPE_GRAMMAR_PARTICLE_FIX = "grammar_particle_fix"
LANGUAGE_JAPANESE = "ja"
# Service traces to monitor flow and results in HA.
logger = logging.getLogger("learn_languages.games.grammar_particle_fix")
PARTICLE_ROMAJI = {
    "は": "wa",
    "を": "o",
    "に": "ni",
    "で": "de",
    "と": "to",
    "が": "ga",
}


@dataclass(frozen=True)
class GrammarParticleItem:
    item_id: str
    sentence_template: str
    romanized_line: str
    literal_translation: str
    choices: list[str]
    correct_particle: str
    explanation: str


@dataclass(frozen=True)
class GrammarParticleAttempt:
    language: str
    item_id: str
    selected_particle: str
    level: int = 1


JAPANESE_PARTICLE_ITEMS_BY_LEVEL: dict[int, list[GrammarParticleItem]] = {
    1: [
        GrammarParticleItem(
            item_id="ja-particle-1-1",
            sentence_template="わたし__ がくせい です。",
            romanized_line="watashi __ gakusei desu.",
            literal_translation="I topic student am",
            choices=["は", "を", "に"],
            correct_particle="は",
            explanation="`は` marks the sentence topic.",
        ),
        GrammarParticleItem(
            item_id="ja-particle-1-2",
            sentence_template="みず__ のみます。",
            romanized_line="mizu __ nomimasu.",
            literal_translation="water object drink",
            choices=["が", "を", "で"],
            correct_particle="を",
            explanation="`を` marks the direct object of a transitive verb.",
        ),
        GrammarParticleItem(
            item_id="ja-particle-1-3",
            sentence_template="がっこう__ いきます。",
            romanized_line="gakkou __ ikimasu.",
            literal_translation="school toward go",
            choices=["に", "は", "と"],
            correct_particle="に",
            explanation="`に` can mark a movement destination.",
        ),
    ],
    2: [
        GrammarParticleItem(
            item_id="ja-particle-2-1",
            sentence_template="きょうしつ__ べんきょう します。",
            romanized_line="kyoushitsu __ benkyou shimasu.",
            literal_translation="in classroom study",
            choices=["で", "に", "が"],
            correct_particle="で",
            explanation="`で` marks the place where an action happens.",
        ),
        GrammarParticleItem(
            item_id="ja-particle-2-2",
            sentence_template="ともだち__ えいが を みます。",
            romanized_line="tomodachi __ eiga o mimasu.",
            literal_translation="with friend movie watch",
            choices=["と", "を", "が"],
            correct_particle="と",
            explanation="`と` is used to do an action with someone.",
        ),
        GrammarParticleItem(
            item_id="ja-particle-2-3",
            sentence_template="ねこ__ すき です。",
            romanized_line="neko __ suki desu.",
            literal_translation="cat subject like",
            choices=["が", "を", "に"],
            correct_particle="が",
            explanation="With `すき`, `が` is normally used for what is liked.",
        ),
    ],
    3: [
        GrammarParticleItem(
            item_id="ja-particle-3-1",
            sentence_template="しごと__ おわって から、うち__ かえります。",
            romanized_line="shigoto __ owatte kara, uchi __ kaerimasu.",
            literal_translation="work subject finishes and then home return",
            choices=["が / に", "を / に", "で / を"],
            correct_particle="が / に",
            explanation="`が` marks the subject of prior state and `に` marks destination.",
        ),
        GrammarParticleItem(
            item_id="ja-particle-3-2",
            sentence_template="この ほん__ よんだ こと が あります。",
            romanized_line="kono hon __ yonda koto ga arimasu.",
            literal_translation="this book object have-experience of reading",
            choices=["を", "が", "で"],
            correct_particle="を",
            explanation="`を` marks the object of `よむ` in this experience expression.",
        ),
    ],
}


class GrammarParticleFixService:
    """Reusable particle-selection service (initial Japanese implementation)."""

    game_type = GAME_TYPE_GRAMMAR_PARTICLE_FIX

    def get_activities(self, language: str, level: int = 1) -> list[GameActivity]:
        logger.debug("activities_request language=%s level=%s", language, level)
        if language != LANGUAGE_JAPANESE:
            logger.info("activities_skipped unsupported_language=%s", language)
            return []

        items = self.get_items(language=language, level=level)
        support = writing_support_profile(level)
        activities = [
            GameActivity(
                activity_id=item.item_id,
                language=language,
                game_type=self.game_type,
                prompt=self._prompt_for_item(item=item, support=support),
                level=level,
            )
            for item in items
        ]
        logger.info("activities_ready language=%s level=%s count=%s", language, level, len(activities))
        return activities

    @staticmethod
    def options_with_romaji(options: list[str]) -> list[dict[str, str]]:
        return [
            {
                "particle": option,
                "romaji": GrammarParticleFixService._romaji_for_option(option),
                "label": f"{option} ({GrammarParticleFixService._romaji_for_option(option)})",
            }
            for option in options
        ]

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

    def get_items(self, language: str, level: int = 1) -> list[GrammarParticleItem]:
        if language != LANGUAGE_JAPANESE:
            logger.info("items_skipped unsupported_language=%s", language)
            return []

        min_level = min(JAPANESE_PARTICLE_ITEMS_BY_LEVEL.keys())
        max_level = max(JAPANESE_PARTICLE_ITEMS_BY_LEVEL.keys())
        normalized_level = min(max(min_level, level), max_level)
        items = JAPANESE_PARTICLE_ITEMS_BY_LEVEL[normalized_level]
        logger.debug("items_ready language=%s requested_level=%s normalized_level=%s count=%s", language, level, normalized_level, len(items))
        return items

    def evaluate_attempt(self, attempt: GrammarParticleAttempt) -> dict:
        logger.info(
            "evaluate_start language=%s level=%s item_id=%s selected_particle=%s",
            attempt.language,
            attempt.level,
            attempt.item_id,
            attempt.selected_particle,
        )
        if attempt.language != LANGUAGE_JAPANESE:
            logger.warning("evaluate_invalid unsupported_language=%s", attempt.language)
            raise ValueError(f"Unsupported language in grammar_particle_fix: {attempt.language}")

        target_item = self._find_item(language=attempt.language, item_id=attempt.item_id, level=attempt.level)

        support = writing_support_profile(attempt.level)
        is_correct = attempt.selected_particle == target_item.correct_particle
        resolved_sentence = self._fill_sentence_template(target_item.sentence_template, attempt.selected_particle)
        result = {
            "game_type": self.game_type,
            "language": attempt.language,
            "item_id": attempt.item_id,
            "selected_particle": attempt.selected_particle,
            "correct_particle": target_item.correct_particle,
            "is_correct": is_correct,
            "score": 100 if is_correct else 0,
            "resolved_sentence": resolved_sentence,
            "literal_translation": target_item.literal_translation,
            "feedback": (
                "Correct. Good particle usage."
                if is_correct
                else f"Review this rule: {target_item.explanation}"
            ),
            "display": self._view_payload(item=target_item, support=support, show_translation=True),
            "retry_state": self._view_payload(
                item=target_item,
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

    @staticmethod
    def _prompt_for_item(item: GrammarParticleItem, support) -> str:
        lines = [f"Fill in the particle: {item.sentence_template}", f"Options: {', '.join(item.choices)}"]
        if support.show_romanized_line:
            lines.append(f"Romanized: {item.romanized_line}")
        if support.show_translation_hint:
            lines.append(f"Translation hint: {item.literal_translation}")
        return "\n".join(lines)

    def _find_item(self, language: str, item_id: str, level: int) -> GrammarParticleItem:
        items = self.get_items(language=language, level=level)
        for item in items:
            if item.item_id == item_id:
                return item
        logger.warning("item_not_found language=%s level=%s item_id=%s", language, level, item_id)
        raise ValueError(f"item_id not found for level {level}: {item_id}")

    @staticmethod
    def _view_payload(
        item: GrammarParticleItem,
        support,
        show_translation: bool,
        hide_translation_hint: bool = False,
    ) -> dict:
        show_translation_hint = bool(support.show_translation_hint and not hide_translation_hint)
        return {
            "show_kanji_line": is_eastern_script("ja"),
            "kanji_line": item.sentence_template,
            "base_line": None,
            "assistance_stage": support.stage,
            "show_romanized_line": bool(support.show_romanized_line),
            "romanized_line": item.romanized_line if support.show_romanized_line else None,
            "show_translation_hint": show_translation_hint,
            "translation_hint": item.literal_translation if show_translation_hint else None,
            "show_literal_translation": show_translation,
            "literal_translation": item.literal_translation if show_translation else None,
            "retry_available": True,
        }

    @staticmethod
    def _romaji_for_option(option: str) -> str:
        parts = [part.strip() for part in option.split("/") if part.strip()]
        romaji_parts = [PARTICLE_ROMAJI.get(part, part) for part in parts]
        return " / ".join(romaji_parts) if romaji_parts else option

    @staticmethod
    def _fill_sentence_template(template: str, selected_particle: str) -> str:
        values = [part.strip() for part in selected_particle.split("/") if part.strip()]
        if not values:
            values = [selected_particle]

        result = template
        for idx in range(result.count("__")):
            replacement = values[idx] if idx < len(values) else values[-1]
            result = result.replace("__", replacement, 1)
        return result
