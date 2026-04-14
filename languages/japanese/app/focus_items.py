from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

FOCUS_ITEM_TYPE_KANJI = "kanji"
FOCUS_ITEM_TYPE_WORD = "word"
FOCUS_ITEM_TYPE_PARTICLE = "particle"
FOCUS_ITEM_TYPE_EXPRESSION = "expression"

ACTIVE_FOCUS_ITEM_TYPES: tuple[str, ...] = (
    FOCUS_ITEM_TYPE_KANJI,
    FOCUS_ITEM_TYPE_WORD,
    FOCUS_ITEM_TYPE_PARTICLE,
)
ALL_FOCUS_ITEM_TYPES: tuple[str, ...] = ACTIVE_FOCUS_ITEM_TYPES + (FOCUS_ITEM_TYPE_EXPRESSION,)


def normalize_focus_item_type(value: str | None, *, fallback: str = FOCUS_ITEM_TYPE_WORD) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ALL_FOCUS_ITEM_TYPES:
        return normalized
    return fallback


def focus_item_type_allowed_for_stage(item_type: str, stage: str | None) -> bool:
    normalized_type = normalize_focus_item_type(item_type)
    normalized_stage = str(stage or "").strip().lower()
    if normalized_type == FOCUS_ITEM_TYPE_EXPRESSION:
        return normalized_stage in {"intermediate", "advanced"}
    return True


def _clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_required_text(value: Any) -> str:
    return str(value or "").strip()


def _slugify_focus_item_id(item_type: str, script: str) -> str:
    normalized_script = re.sub(r"\s+", "-", script.strip())
    normalized_script = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff-]+", "", normalized_script)
    normalized_script = normalized_script[:48].strip("-")
    if not normalized_script:
        normalized_script = "item"
    return f"{item_type}-{normalized_script}"


@dataclass(frozen=True)
class FocusItem:
    """Lesson-side lexical or grammar item that games can later reuse."""

    item_id: str
    item_type: str
    script: str
    reading_kana: str | None = None
    reading_romanized: str | None = None
    meaning_en: str | None = None
    meaning_secondary: str | None = None
    function: str | None = None
    example_script: str | None = None
    example_romanized: str | None = None
    example_literal_translation: str | None = None
    level_hint: int | None = None
    is_core: bool = False
    is_exam_relevant: bool = False
    covers_competencies: tuple[str, ...] = ()
    source: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "script": self.script,
            "reading_kana": self.reading_kana,
            "reading_romanized": self.reading_romanized,
            "meaning_en": self.meaning_en,
            "meaning_secondary": self.meaning_secondary,
            "function": self.function,
            "example_script": self.example_script,
            "example_romanized": self.example_romanized,
            "example_literal_translation": self.example_literal_translation,
            "level_hint": self.level_hint,
            "is_core": self.is_core,
            "is_exam_relevant": self.is_exam_relevant,
            "covers_competencies": list(self.covers_competencies),
            "source": self.source,
        }


def normalize_focus_item(raw: Any) -> FocusItem | None:
    if not isinstance(raw, dict):
        return None

    item_type = normalize_focus_item_type(raw.get("item_type"))
    script = _clean_required_text(raw.get("script"))
    if not script:
        return None

    meaning_en = _clean_optional_text(raw.get("meaning_en"))
    function = _clean_optional_text(raw.get("function"))
    if not meaning_en and not function:
        return None

    item_id = _clean_optional_text(raw.get("item_id")) or _slugify_focus_item_id(item_type, script)
    level_hint_raw = raw.get("level_hint")
    level_hint: int | None = None
    if level_hint_raw not in (None, ""):
        try:
            level_hint = int(level_hint_raw)
        except (TypeError, ValueError):
            level_hint = None
    covers_competencies_raw = raw.get("covers_competencies")
    covers_competencies: tuple[str, ...] = ()
    if isinstance(covers_competencies_raw, (list, tuple)):
        covers_competencies = tuple(
            str(item).strip() for item in covers_competencies_raw if str(item).strip()
        )

    return FocusItem(
        item_id=item_id,
        item_type=item_type,
        script=script,
        reading_kana=_clean_optional_text(raw.get("reading_kana")),
        reading_romanized=_clean_optional_text(raw.get("reading_romanized")),
        meaning_en=meaning_en,
        meaning_secondary=_clean_optional_text(raw.get("meaning_secondary")),
        function=function,
        example_script=_clean_optional_text(raw.get("example_script")),
        example_romanized=_clean_optional_text(raw.get("example_romanized")),
        example_literal_translation=_clean_optional_text(raw.get("example_literal_translation")),
        level_hint=level_hint,
        is_core=bool(raw.get("is_core") or raw.get("mandatory")),
        is_exam_relevant=bool(raw.get("is_exam_relevant") or raw.get("exam_relevant")),
        covers_competencies=covers_competencies,
        source=_clean_optional_text(raw.get("source")),
    )


def normalize_focus_items(raw: Any, *, stage: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for entry in raw:
        item = normalize_focus_item(entry)
        if item is None:
            continue
        if not focus_item_type_allowed_for_stage(item.item_type, stage):
            continue
        normalized.append(item.to_payload())
    return normalized
