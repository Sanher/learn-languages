from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from random import Random
from typing import Any

GAME_TYPE_KANJI_READING_MATCH = "kanji_reading_match"
LANGUAGE_JAPANESE = "ja"

logger = logging.getLogger("learn_languages.games.kanji_reading_match")

_KANJI_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _contains_kanji(value: str) -> bool:
    return bool(_KANJI_PATTERN.search(str(value or "")))


@dataclass(frozen=True)
class KanjiReadingMatchItem:
    item_id: str
    item_type: str
    script: str
    reading_romanized: str
    reading_kana: str | None = None
    meaning: str | None = None
    is_core: bool = False
    is_exam_relevant: bool = False


@dataclass(frozen=True)
class KanjiReadingMatchOption:
    option_id: str
    reading_romanized: str


@dataclass(frozen=True)
class KanjiReadingMatchRound:
    item: KanjiReadingMatchItem
    prompt: str
    options: tuple[KanjiReadingMatchOption, ...]
    correct_option_id: str


@dataclass(frozen=True)
class KanjiReadingMatchAttempt:
    language: str
    item_id: str
    script: str
    selected_option_id: str
    correct_option_id: str
    correct_reading_romanized: str
    correct_reading_kana: str | None = None
    meaning: str | None = None
    level: int = 1


class KanjiReadingMatchService:
    game_type = GAME_TYPE_KANJI_READING_MATCH

    def eligible_items(self, focus_items: list[dict[str, Any]]) -> list[KanjiReadingMatchItem]:
        items: list[KanjiReadingMatchItem] = []
        seen_ids: set[str] = set()
        for raw in focus_items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or "").strip()
            script = str(raw.get("script") or "").strip()
            reading_romanized = str(raw.get("reading_romanized") or "").strip()
            item_type = str(raw.get("item_type") or "word").strip().lower()
            if not item_id or not script or not reading_romanized:
                continue
            if item_type not in {"kanji", "word", "expression"}:
                continue
            if not _contains_kanji(script):
                continue
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            items.append(
                KanjiReadingMatchItem(
                    item_id=item_id,
                    item_type=item_type,
                    script=script,
                    reading_romanized=reading_romanized,
                    reading_kana=str(raw.get("reading_kana") or "").strip() or None,
                    meaning=str(raw.get("meaning_en") or "").strip() or None,
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
    ) -> KanjiReadingMatchRound | None:
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

        distractors = [item for item in items if item.item_id != target.item_id and item.reading_romanized != target.reading_romanized]
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
        option_values = [target.reading_romanized, *[item.reading_romanized for item in selected_distractors]]
        option_seed.shuffle(option_values)

        options: list[KanjiReadingMatchOption] = []
        correct_option_id = ""
        for index, reading in enumerate(option_values, start=1):
            option_id = f"reading-{index}"
            options.append(KanjiReadingMatchOption(option_id=option_id, reading_romanized=reading))
            if reading == target.reading_romanized:
                correct_option_id = option_id

        if not correct_option_id:
            logger.warning("round_invalid_missing_correct_option item_id=%s", target.item_id)
            return None

        return KanjiReadingMatchRound(
            item=target,
            prompt="Choose the correct romanized reading for this kanji or word.",
            options=tuple(options),
            correct_option_id=correct_option_id,
        )

    def round_payload(self, round_data: KanjiReadingMatchRound) -> dict[str, Any]:
        return {
            "item_id": round_data.item.item_id,
            "script": round_data.item.script,
            "item_type": round_data.item.item_type,
            "reading_kana": round_data.item.reading_kana,
            "meaning": round_data.item.meaning or "",
            "is_core": round_data.item.is_core,
            "is_exam_relevant": round_data.item.is_exam_relevant,
            "correct_option_id": round_data.correct_option_id,
            "correct_reading": round_data.item.reading_romanized,
            "correct_reading_kana": round_data.item.reading_kana or "",
            "options": [
                {
                    "option_id": option.option_id,
                    "reading_romanized": option.reading_romanized,
                }
                for option in round_data.options
            ],
        }

    def evaluate_attempt(self, attempt: KanjiReadingMatchAttempt) -> dict[str, Any]:
        if attempt.language != LANGUAGE_JAPANESE:
            raise ValueError(f"Unsupported language in kanji_reading_match: {attempt.language}")

        is_correct = str(attempt.selected_option_id).strip() == str(attempt.correct_option_id).strip()
        score = 100 if is_correct else 0
        feedback = (
            f"Correct. {attempt.script} is read as {attempt.correct_reading_romanized}."
            if is_correct
            else f"Not quite. {attempt.script} is read as {attempt.correct_reading_romanized}."
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
            "correct_reading": attempt.correct_reading_romanized,
            "correct_reading_kana": attempt.correct_reading_kana or "",
            "meaning": attempt.meaning or "",
            "feedback": feedback,
        }
