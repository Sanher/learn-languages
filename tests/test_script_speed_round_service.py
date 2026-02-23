import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    ALIAS_GAME_TYPE_KANA_SPEED_ROUND,
    GAME_TYPE_SCRIPT_SPEED_ROUND,
    GameServiceRegistry,
    KanaSpeedRoundService,
    ScriptSpeedAttempt,
    ScriptSpeedRoundService,
)


class ScriptSpeedRoundServiceTests(unittest.TestCase):
    def test_generic_service_supports_western_alphabet(self) -> None:
        service = ScriptSpeedRoundService()
        activities = service.get_activities(language="en", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_SCRIPT_SPEED_ROUND)

    def test_alias_kana_service_is_japanese_only(self) -> None:
        service = KanaSpeedRoundService()
        ja_activities = service.get_activities(language="ja", level=1)
        en_activities = service.get_activities(language="en", level=1)
        self.assertTrue(ja_activities)
        self.assertEqual(en_activities, [])
        self.assertEqual(ja_activities[0].game_type, ALIAS_GAME_TYPE_KANA_SPEED_ROUND)
        self.assertIn("Romaji guide", ja_activities[0].prompt)

    def test_kana_advanced_hides_romaji_guide(self) -> None:
        service = KanaSpeedRoundService()
        ja_activities = service.get_activities(language="ja", level=3)
        self.assertTrue(ja_activities)
        self.assertNotIn("Romaji guide", ja_activities[0].prompt)

    def test_evaluate_attempt(self) -> None:
        service = ScriptSpeedRoundService()
        result = service.evaluate_attempt(
            ScriptSpeedAttempt(
                language="en",
                sequence_expected=["a", "b", "c", "d", "e"],
                sequence_read=["a", "b", "x", "d", "e"],
                elapsed_seconds=3.0,
                level=1,
            )
        )
        self.assertIn("score", result)
        self.assertIn("metrics", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_kana_audio_attempt_uses_pronunciation_metrics_and_retry_alert(self) -> None:
        service = KanaSpeedRoundService()
        result = service.evaluate_attempt(
            ScriptSpeedAttempt(
                language="ja",
                sequence_expected=[],
                sequence_read=[],
                elapsed_seconds=3.0,
                level=1,
                expected_text="あ い う え お",
                recognized_text="あ い う え お",
                audio_duration_seconds=3.0,
                speech_seconds=2.8,
                pause_seconds=0.2,
                pitch_track_hz=[150.0, 149.0, 151.0],
                retry_count=3,
            )
        )
        self.assertIn("pronunciation_confidence", result["metrics"])
        self.assertIn("speech_rate_wpm", result["metrics"])
        self.assertIn("expected_romaji", result)
        self.assertIn("recognized_romaji", result)
        self.assertIn("expected_translation", result)
        self.assertIn("recognized_translation", result)
        self.assertIn("sequence_mismatches", result)
        self.assertGreaterEqual(result["score"], 80)
        self.assertEqual(result["retry_count"], 3)
        self.assertTrue(result["alerts"])

    def test_kana_audio_without_spaces_is_tokenized(self) -> None:
        service = KanaSpeedRoundService()
        result = service.evaluate_attempt(
            ScriptSpeedAttempt(
                language="ja",
                sequence_expected=[],
                sequence_read=[],
                elapsed_seconds=3.0,
                level=1,
                expected_text="あいうえお",
                recognized_text="あいうえお",
            )
        )
        self.assertGreaterEqual(result["metrics"]["accuracy"], 0.8)

    def test_alias_is_reusable_through_registry_for_kana_game_type(self) -> None:
        registry = GameServiceRegistry()
        registry.register(KanaSpeedRoundService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[ALIAS_GAME_TYPE_KANA_SPEED_ROUND],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(ALIAS_GAME_TYPE_KANA_SPEED_ROUND, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
