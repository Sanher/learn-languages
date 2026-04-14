from __future__ import annotations

from dataclasses import dataclass
import logging
from random import Random
from typing import Any

GAME_TYPE_MEANING_MATCH = "meaning_match"
LANGUAGE_JAPANESE = "ja"

logger = logging.getLogger("learn_languages.games.meaning_match")


@dataclass(frozen=True)
class MeaningMatchItem:
    item_id: str
    item_type: str
    script: str
    meaning: str
    reading_romanized: str | None = None
    reading_kana: str | None = None
    is_core: bool = False
    is_exam_relevant: bool = False


@dataclass(frozen=True)
class MeaningMatchOption:
    option_id: str
    meaning: str


@dataclass(frozen=True)
class MeaningMatchRound:
    item: MeaningMatchItem
    prompt: str
    options: tuple[MeaningMatchOption, ...]
    correct_option_id: str


@dataclass(frozen=True)
class MeaningMatchAttempt:
    language: str
    item_id: str
    script: str
    selected_option_id: str
    correct_option_id: str
    correct_meaning: str
    reading_romanized: str | None = None
    reading_kana: str | None = None
    level: int = 1


class MeaningMatchService:
    game_type = GAME_TYPE_MEANING_MATCH

    def eligible_items(self, focus_items: list[dict[str, Any]]) -> list[MeaningMatchItem]:
        items: list[MeaningMatchItem] = []
        seen_ids: set[str] = set()
        seen_meanings: set[str] = set()
        for raw in focus_items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or "").strip()
            script = str(raw.get("script") or "").strip()
            meaning = str(raw.get("meaning_en") or "").strip()
            item_type = str(raw.get("item_type") or "word").strip().lower()
            if not item_id or not script or not meaning:
                continue
            if item_type not in {"kanji", "word", "expression"}:
                continue
            normalized_meaning = meaning.casefold()
            if item_id in seen_ids or normalized_meaning in seen_meanings:
                continue
            seen_ids.add(item_id)
            seen_meanings.add(normalized_meaning)
            items.append(
                MeaningMatchItem(
                    item_id=item_id,
                    item_type=item_type,
                    script=script,
                    meaning=meaning,
                    reading_romanized=str(raw.get("reading_romanized") or "").strip() or None,
                    reading_kana=str(raw.get("reading_kana") or "").strip() or None,
                    is_core=bool(raw.get("is_core")),
                    is_exam_relevant=bool(raw.get("is_exam_relevant")),
                )
            )
        logger.info("eligible_items_ready count=%s", len(items))
        return items

    def build_round(
        self,
        *,
        focus_items: list[dict[str, Any]],
        seed: str,
        item_id: str | None = None,
    ) -> MeaningMatchRound | None:
        items = self.eligible_items(focus_items)
        if len(items) < 3:
            logger.info("round_skipped reason=not_enough_items count=%s", len(items))
            return None

        target = None
        if item_id:
            target = next((item for item in items if item.item_id == item_id), None)
            if target is None:
                logger.info("round_skipped reason=item_not_found item_id=%s", item_id)
                return None
        else:
            rnd = Random(seed)
            target = items[rnd.randrange(len(items))]

        distractors = [item for item in items if item.item_id != target.item_id and item.meaning != target.meaning]
        if len(distractors) < 2:
            logger.info(
                "round_skipped reason=not_enough_distractors item_id=%s distractors=%s",
                target.item_id,
                len(distractors),
            )
            return None

        distractors = sorted(distractors, key=lambda item: (item.script, item.item_id))
        option_seed = Random(f"{seed}:{target.item_id}")
        option_seed.shuffle(distractors)
        selected_distractors = distractors[: min(3, len(distractors))]
        option_values = [target.meaning, *[item.meaning for item in selected_distractors]]
        option_seed.shuffle(option_values)

        options: list[MeaningMatchOption] = []
        correct_option_id = ""
        for index, meaning in enumerate(option_values, start=1):
            option_id = f"meaning-{index}"
            options.append(MeaningMatchOption(option_id=option_id, meaning=meaning))
            if meaning == target.meaning:
                correct_option_id = option_id

        if not correct_option_id:
            logger.warning("round_invalid_missing_correct_option item_id=%s", target.item_id)
            return None

        return MeaningMatchRound(
            item=target,
            prompt="Choose the correct English meaning for this Japanese item.",
            options=tuple(options),
            correct_option_id=correct_option_id,
        )

    def round_payload(self, round_data: MeaningMatchRound) -> dict[str, Any]:
        return {
            "item_id": round_data.item.item_id,
            "script": round_data.item.script,
            "item_type": round_data.item.item_type,
            "reading_romanized": round_data.item.reading_romanized or "",
            "reading_kana": round_data.item.reading_kana or "",
            "is_core": round_data.item.is_core,
            "is_exam_relevant": round_data.item.is_exam_relevant,
            "correct_option_id": round_data.correct_option_id,
            "correct_meaning": round_data.item.meaning,
            "options": [
                {
                    "option_id": option.option_id,
                    "meaning": option.meaning,
                }
                for option in round_data.options
            ],
        }

    def evaluate_attempt(self, attempt: MeaningMatchAttempt) -> dict[str, Any]:
        if attempt.language != LANGUAGE_JAPANESE:
            raise ValueError(f"Unsupported language in meaning_match: {attempt.language}")

        is_correct = str(attempt.selected_option_id).strip() == str(attempt.correct_option_id).strip()
        score = 100 if is_correct else 0
        feedback = (
            f"Correct. {attempt.script} means {attempt.correct_meaning}."
            if is_correct
            else f"Not quite. {attempt.script} means {attempt.correct_meaning}."
        )
        logger.info(
            "evaluate_done item_id=%s score=%s is_correct=%s selected_option=%s",
            attempt.item_id,
            score,
            is_correct,
            attempt.selected_option_id,
        )
        return {
            "game_type": self.game_type,
            "language": attempt.language,
            "score": score,
            "accuracy": 1.0 if is_correct else 0.0,
            "is_correct": is_correct,
            "item_id": attempt.item_id,
            "script": attempt.script,
            "selected_option_id": attempt.selected_option_id,
            "correct_option_id": attempt.correct_option_id,
            "correct_meaning": attempt.correct_meaning,
            "reading_romanized": attempt.reading_romanized or "",
            "reading_kana": attempt.reading_kana or "",
            "feedback": feedback,
            "meaning": attempt.correct_meaning,
        }
