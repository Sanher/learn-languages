from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
import re
from typing import Iterable
import unicodedata

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


def _is_japanese_language(language: str | None) -> bool:
    return (language or "").strip().lower() == "ja"


def _normalize_text(text: str, language: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").strip()
    if _is_japanese_language(language):
        normalized = re.sub(r"[\s。、，「」『』・！？!?\-]", "", normalized)
        return normalized
    return " ".join(normalized.lower().split())


def _word_overlap(expected: list[str], recognized: list[str], language: str | None) -> float:
    if not expected:
        return 0.0

    if _is_japanese_language(language):
        normalized_recognized = _normalize_text("".join(recognized), language)
        if not normalized_recognized:
            return 0.0
        matches = 0
        for token in expected:
            normalized_token = _normalize_text(token, language)
            if normalized_token and normalized_token in normalized_recognized:
                matches += 1
        return matches / len(expected)

    recognized_set = {_normalize_text(token, language) for token in recognized}
    matches = sum(1 for token in expected if _normalize_text(token, language) in recognized_set)
    return matches / len(expected)


def _character_similarity(expected_text: str, recognized_text: str, language: str | None) -> float:
    normalized_expected = _normalize_text(expected_text, language)
    normalized_recognized = _normalize_text(recognized_text, language)
    if not normalized_expected or not normalized_recognized:
        return 0.0
    return SequenceMatcher(a=normalized_expected, b=normalized_recognized).ratio()


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


def _build_word_feedback(expected: list[str], recognized: list[str], language: str | None) -> list[WordFeedback]:
    feedback: list[WordFeedback] = []
    if _is_japanese_language(language):
        recognized_full = _normalize_text("".join(recognized), language)
        for token in expected:
            normalized_token = _normalize_text(token, language)
            if normalized_token and normalized_token not in recognized_full:
                feedback.append(
                    WordFeedback(
                        word=token,
                        issue="omitted or mispronounced segment",
                        hint="Repeat this segment in isolation three times before retrying the full sentence.",
                    )
                )
        if not feedback and expected and recognized:
            normalized_expected = _normalize_text("".join(expected), language)
            if normalized_expected != recognized_full:
                feedback.append(
                    WordFeedback(
                        word=expected[-1],
                        issue="segment connection or vowel length can be improved",
                        hint="Keep a steady rhythm and pay attention to long vowels and consonant links.",
                    )
                )
        return feedback[:3]

    recognized_set = {_normalize_text(token, language) for token in recognized}

    for token in expected:
        if _normalize_text(token, language) not in recognized_set:
            feedback.append(
                WordFeedback(
                    word=token,
                    issue="omitted or mispronounced word",
                    hint="Repeat this word in isolation three times before retrying the full sentence.",
                )
            )

    if not feedback and expected and recognized and expected != recognized:
        feedback.append(
            WordFeedback(
                word=expected[-1],
                issue="word rhythm/connection can be improved",
                hint="Keep a steady flow and avoid long pauses.",
            )
        )

    return feedback[:3]


def run_pronunciation_activity(request: PronunciationRequest, current_date: date) -> dict:
    expected_words = _tokenize(request.expected_text)
    recognized_words = _tokenize(request.recognized_text)
    language = request.language or language_for_date(current_date)

    overlap = _word_overlap(expected_words, recognized_words, language)
    char_similarity = _character_similarity(request.expected_text, request.recognized_text, language)
    pause_ratio = 0.0 if request.audio_duration_seconds <= 0 else min(1.0, request.pause_seconds / request.audio_duration_seconds)
    pitch_stability = _pitch_stability(request.pitch_track_hz)

    if _is_japanese_language(language):
        pronunciation_confidence = max(
            0.0,
            min(
                1.0,
                (char_similarity * 0.75) + (overlap * 0.15) + (pitch_stability * 0.05) + ((1 - pause_ratio) * 0.05),
            ),
        )
    else:
        pronunciation_confidence = max(
            0.0,
            min(
                1.0,
                (overlap * 0.6) + (pitch_stability * 0.25) + ((1 - pause_ratio) * 0.15),
            ),
        )

    feedback = _build_word_feedback(expected_words, recognized_words, language)

    return {
        "activity_type": request.activity_type,
        "language": language,
        "expected_text": request.expected_text,
        "recognized_text": request.recognized_text,
        "metrics": {
            "pronunciation_confidence": round(pronunciation_confidence, 2),
            "character_similarity": round(char_similarity, 2),
            "token_overlap": round(overlap, 2),
            "speech_rate_wpm": _speech_rate_wpm(recognized_words, request.speech_seconds),
            "pause_ratio": round(pause_ratio, 2),
            "pitch_stability": round(pitch_stability, 2),
        },
        "word_feedback": [feedback_item.__dict__ for feedback_item in feedback],
        "next_step": "Repeat the sentence three times with continuous rhythm." if feedback else "Move to the next sentence.",
    }
