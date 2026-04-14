from __future__ import annotations

from dataclasses import dataclass
import logging
from random import Random
from typing import Any

GAME_TYPE_PARTICLE_FUNCTION_MATCH = "particle_function_match"
LANGUAGE_JAPANESE = "ja"

logger = logging.getLogger("learn_languages.games.particle_function_match")

_PARTICLE_FUNCTION_LABELS = {
    "は": "Topic marker",
    "が": "Subject marker",
    "を": "Direct object marker",
    "に": "Destination / time marker",
    "で": "Location / means marker",
    "へ": "Direction marker",
    "と": "With / and marker",
    "の": "Possession marker",
    "も": "Also marker",
    "か": "Question marker",
}


def _function_label_for_particle(script: str, function_text: str) -> str:
    if script in _PARTICLE_FUNCTION_LABELS:
        return _PARTICLE_FUNCTION_LABELS[script]
    text = str(function_text or "").strip().rstrip(".")
    if not text:
        return "Grammar marker"
    if text.startswith("Marks "):
        text = text[len("Marks ") :]
    if text.startswith("Turns "):
        text = text[len("Turns ") :]
    return text[:1].upper() + text[1:]


@dataclass(frozen=True)
class ParticleFunctionMatchItem:
    item_id: str
    script: str
    function_label: str
    function_explanation: str
    reading_romanized: str | None = None
    reading_kana: str | None = None
    is_core: bool = False
    is_exam_relevant: bool = False


@dataclass(frozen=True)
class ParticleFunctionMatchOption:
    option_id: str
    label: str


@dataclass(frozen=True)
class ParticleFunctionMatchRound:
    item: ParticleFunctionMatchItem
    prompt: str
    options: tuple[ParticleFunctionMatchOption, ...]
    correct_option_id: str


@dataclass(frozen=True)
class ParticleFunctionMatchAttempt:
    language: str
    item_id: str
    script: str
    selected_option_id: str
    correct_option_id: str
    correct_function_label: str
    function_explanation: str
    reading_romanized: str | None = None
    reading_kana: str | None = None
    level: int = 1


class ParticleFunctionMatchService:
    game_type = GAME_TYPE_PARTICLE_FUNCTION_MATCH

    def eligible_items(self, focus_items: list[dict[str, Any]]) -> list[ParticleFunctionMatchItem]:
        items: list[ParticleFunctionMatchItem] = []
        seen_ids: set[str] = set()
        seen_labels: dict[str, str] = {}
        for raw in focus_items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("item_id") or "").strip()
            script = str(raw.get("script") or "").strip()
            item_type = str(raw.get("item_type") or "").strip().lower()
            function_text = str(raw.get("function") or "").strip()
            if item_type != "particle" or not item_id or not script or not function_text:
                continue
            if item_id in seen_ids:
                continue
            function_label = _function_label_for_particle(script, function_text)
            seen_ids.add(item_id)
            # Keep only one item per concise function label so options remain distinct.
            if function_label in seen_labels:
                continue
            seen_labels[function_label] = item_id
            items.append(
                ParticleFunctionMatchItem(
                    item_id=item_id,
                    script=script,
                    function_label=function_label,
                    function_explanation=function_text,
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
    ) -> ParticleFunctionMatchRound | None:
        items = self.eligible_items(focus_items)
        if len(items) < 3:
            logger.info("round_skipped reason=not_enough_items count=%s", len(items))
            return None

        if item_id:
            target = next((item for item in items if item.item_id == item_id), None)
            if target is None:
                logger.info("round_skipped reason=item_not_found item_id=%s", item_id)
                return None
        else:
            rnd = Random(seed)
            target = items[rnd.randrange(len(items))]

        distractors = [item for item in items if item.item_id != target.item_id and item.function_label != target.function_label]
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
        option_values = [target.function_label, *[item.function_label for item in selected_distractors]]
        option_seed.shuffle(option_values)

        options: list[ParticleFunctionMatchOption] = []
        correct_option_id = ""
        for index, label in enumerate(option_values, start=1):
            option_id = f"particle-function-{index}"
            options.append(ParticleFunctionMatchOption(option_id=option_id, label=label))
            if label == target.function_label:
                correct_option_id = option_id

        if not correct_option_id:
            logger.warning("round_invalid_missing_correct_option item_id=%s", target.item_id)
            return None

        return ParticleFunctionMatchRound(
            item=target,
            prompt="Choose the core function that best matches this Japanese particle.",
            options=tuple(options),
            correct_option_id=correct_option_id,
        )

    def round_payload(self, round_data: ParticleFunctionMatchRound) -> dict[str, Any]:
        return {
            "item_id": round_data.item.item_id,
            "script": round_data.item.script,
            "item_type": "particle",
            "reading_romanized": round_data.item.reading_romanized or "",
            "reading_kana": round_data.item.reading_kana or "",
            "is_core": round_data.item.is_core,
            "is_exam_relevant": round_data.item.is_exam_relevant,
            "correct_option_id": round_data.correct_option_id,
            "correct_function": round_data.item.function_label,
            "explanation": round_data.item.function_explanation,
            "meaning": round_data.item.function_label,
            "options": [
                {
                    "option_id": option.option_id,
                    "label": option.label,
                }
                for option in round_data.options
            ],
        }

    def evaluate_attempt(self, attempt: ParticleFunctionMatchAttempt) -> dict[str, Any]:
        if attempt.language != LANGUAGE_JAPANESE:
            raise ValueError(f"Unsupported language in particle_function_match: {attempt.language}")

        is_correct = str(attempt.selected_option_id).strip() == str(attempt.correct_option_id).strip()
        score = 100 if is_correct else 0
        feedback = (
            f"Correct. {attempt.script} works here as a {attempt.correct_function_label.lower()}."
            if is_correct
            else f"Not quite. {attempt.script} works here as a {attempt.correct_function_label.lower()}."
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
            "reading_romanized": attempt.reading_romanized or "",
            "reading_kana": attempt.reading_kana or "",
            "feedback": feedback,
            "meaning": attempt.correct_function_label,
            "explanation": attempt.function_explanation,
        }
