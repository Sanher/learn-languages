from datetime import date
import unittest

from language_games.policy import language_for_date
from language_games.pronunciation import PronunciationRequest, run_pronunciation_activity


class PronunciationPipelineTests(unittest.TestCase):
    def test_policy_weekday_and_weekend(self) -> None:
        self.assertEqual(language_for_date(date(2026, 2, 13)), "ja")  # Friday
        self.assertEqual(language_for_date(date(2026, 2, 14)), "en")  # Saturday

    def test_pronunciation_activity_response_shape(self) -> None:
        request = PronunciationRequest(
            expected_text="hello world",
            recognized_text="hello world",
            audio_duration_seconds=2.0,
            speech_seconds=1.8,
            pause_seconds=0.2,
            pitch_track_hz=[150.0, 155.0, 148.0, 152.0],
        )

        response = run_pronunciation_activity(request, current_date=date(2026, 2, 14))

        self.assertEqual(response["activity_type"], "pronunciation_guided")
        self.assertEqual(response["language"], "en")
        self.assertEqual(response["expected_text"], "hello world")
        self.assertEqual(response["recognized_text"], "hello world")
        self.assertIn("metrics", response)
        self.assertIn("word_feedback", response)
        self.assertGreaterEqual(response["metrics"]["pronunciation_confidence"], 0)
        self.assertLessEqual(response["metrics"]["pronunciation_confidence"], 1)

    def test_missing_word_generates_feedback(self) -> None:
        request = PronunciationRequest(
            expected_text="good morning everyone",
            recognized_text="good morning",
            audio_duration_seconds=3.0,
            speech_seconds=2.0,
            pause_seconds=0.6,
            pitch_track_hz=[120.0, 124.0, 122.0],
        )

        response = run_pronunciation_activity(request, current_date=date(2026, 2, 11))

        self.assertTrue(response["word_feedback"])
        self.assertIn("everyone", [item["word"] for item in response["word_feedback"]])
        self.assertEqual(response["next_step"], "Repeat the sentence three times with continuous rhythm.")

    def test_japanese_text_without_spaces_still_scores_high(self) -> None:
        request = PronunciationRequest(
            expected_text="日本語 の 発音 を 毎日 練習 しています",
            recognized_text="日本語の発音を毎日練習しています。",
            audio_duration_seconds=7.1,
            speech_seconds=7.1,
            pause_seconds=0.2,
            pitch_track_hz=[150.0, 151.0, 149.0],
            language="ja",
        )

        response = run_pronunciation_activity(request, current_date=date(2026, 4, 14))

        self.assertGreaterEqual(response["metrics"]["pronunciation_confidence"], 0.9)
        self.assertGreaterEqual(response["metrics"]["character_similarity"], 0.95)
        self.assertEqual(response["metrics"]["token_overlap"], 1.0)
        self.assertFalse(response["word_feedback"])


if __name__ == "__main__":
    unittest.main()
