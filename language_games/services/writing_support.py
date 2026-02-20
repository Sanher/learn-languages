from __future__ import annotations

from dataclasses import dataclass

EASTERN_SCRIPT_LANGUAGE_CODES = {"ja", "zh", "ko"}


@dataclass(frozen=True)
class WritingSupportProfile:
    stage: str
    show_options: bool
    show_romanized_line: bool
    show_translation_hint: bool


def writing_support_profile(level: int) -> WritingSupportProfile:
    """Define ayudas de escritura segun progreso (nivel)."""
    if level <= 1:
        return WritingSupportProfile(
            stage="beginner",
            show_options=True,
            show_romanized_line=True,
            show_translation_hint=True,
        )
    if level == 2:
        return WritingSupportProfile(
            stage="intermediate",
            show_options=False,
            show_romanized_line=True,
            show_translation_hint=False,
        )
    return WritingSupportProfile(
        stage="advanced",
        show_options=False,
        show_romanized_line=False,
        show_translation_hint=False,
    )


def is_eastern_script(language: str) -> bool:
    return language in EASTERN_SCRIPT_LANGUAGE_CODES
