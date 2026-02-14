from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .policy import language_for_date


@dataclass(frozen=True)
class PronunciationRequest:
    expected_text: str
    recognized_text: str
    audio_duration_seconds: float
    speech_seconds: float
    pause_seconds: float
    pitch_track_hz: list[float]
    activity_type: str = "pronunciation_guided"
    language: str | None = None


@dataclass(frozen=True)
class WordFeedback:
    word: str
    issue: str
    hint: str


def _tokenize(text: str) -> list[str]:
    return [token.strip() for token in text.split() if token.strip()]


def _word_overlap(expected: list[str], recognized: list[str]) -> float:
    if not expected:
        return 0.0
    recognized_set = set(recognized)
    matches = sum(1 for token in expected if token in recognized_set)
    return matches / len(expected)


def _pitch_stability(pitch_track_hz: Iterable[float]) -> float:
    values = [p for p in pitch_track_hz if p > 0]
    if len(values) < 2:
        return 0.0

    mean_pitch = sum(values) / len(values)
    variance = sum((p - mean_pitch) ** 2 for p in values) / len(values)
    std_dev = variance**0.5

    # Map lower deviation to higher stability on [0..1]
    return max(0.0, min(1.0, 1.0 - (std_dev / max(mean_pitch, 1.0))))


def _speech_rate_wpm(recognized_words: list[str], speech_seconds: float) -> int:
    if speech_seconds <= 0:
        return 0
    return round((len(recognized_words) / speech_seconds) * 60)


def _build_word_feedback(expected: list[str], recognized: list[str]) -> list[WordFeedback]:
    feedback: list[WordFeedback] = []
    recognized_set = set(recognized)

    for token in expected:
        if token not in recognized_set:
            feedback.append(
                WordFeedback(
                    word=token,
                    issue="palabra omitida o mal pronunciada",
                    hint="Repite esta palabra de forma aislada 3 veces antes de rehacer la frase.",
                )
            )

    if not feedback and expected and recognized and expected != recognized:
        feedback.append(
            WordFeedback(
                word=expected[-1],
                issue="ritmo o unión entre palabras mejorable",
                hint="Intenta mantener un ritmo continuo sin pausas largas.",
            )
        )

    return feedback[:3]


def run_pronunciation_activity(request: PronunciationRequest, current_date: date) -> dict:
    expected_words = _tokenize(request.expected_text)
    recognized_words = _tokenize(request.recognized_text)

    overlap = _word_overlap(expected_words, recognized_words)
    pause_ratio = 0.0 if request.audio_duration_seconds <= 0 else min(1.0, request.pause_seconds / request.audio_duration_seconds)
    pitch_stability = _pitch_stability(request.pitch_track_hz)

    pronunciation_confidence = max(
        0.0,
        min(
            1.0,
            (overlap * 0.6) + (pitch_stability * 0.25) + ((1 - pause_ratio) * 0.15),
        ),
    )

    feedback = _build_word_feedback(expected_words, recognized_words)
    language = request.language or language_for_date(current_date)

    return {
        "activity_type": request.activity_type,
        "language": language,
        "expected_text": request.expected_text,
        "recognized_text": request.recognized_text,
        "metrics": {
            "pronunciation_confidence": round(pronunciation_confidence, 2),
            "speech_rate_wpm": _speech_rate_wpm(recognized_words, request.speech_seconds),
            "pause_ratio": round(pause_ratio, 2),
            "pitch_stability": round(pitch_stability, 2),
        },
        "word_feedback": [feedback_item.__dict__ for feedback_item in feedback],
        "next_step": "Repite la frase 3 veces con ritmo continuo." if feedback else "Pasa a la siguiente frase.",
    }
