import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_PRONUNCIATION_MATCH,
    GameServiceRegistry,
    PronunciationMatchAttempt,
    PronunciationMatchService,
)


class PronunciationMatchServiceTests(unittest.TestCase):
    def test_japanese_activities_are_available(self) -> None:
        service = PronunciationMatchService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_PRONUNCIATION_MATCH)

    def test_beginner_and_intermediate_show_romanized(self) -> None:
        service = PronunciationMatchService()
        beginner_activity = service.get_activities(language="ja", level=1)[0]
        intermediate_activity = service.get_activities(language="ja", level=2)[0]

        beginner_view = service.build_attempt_view(
            language="ja",
            item_id=beginner_activity.activity_id,
            level=1,
            show_translation=False,
        )
        intermediate_view = service.build_attempt_view(
            language="ja",
            item_id=intermediate_activity.activity_id,
            level=2,
            show_translation=False,
        )
        self.assertTrue(beginner_view["show_romanized_line"])
        self.assertTrue(intermediate_view["show_romanized_line"])
        self.assertTrue(beginner_view["romanized_line"])
        self.assertTrue(intermediate_view["romanized_line"])

    def test_advanced_hides_romanized(self) -> None:
        service = PronunciationMatchService()
        activity = service.get_activities(language="ja", level=3)[0]
        view = service.build_attempt_view(
            language="ja",
            item_id=activity.activity_id,
            level=3,
            show_translation=False,
        )
        self.assertFalse(view["show_romanized_line"])
        self.assertIsNone(view["romanized_line"])

    def test_evaluate_attempt_returns_match_fields(self) -> None:
        service = PronunciationMatchService()
        activity = service.get_activities(language="ja", level=1)[0]
        view = service.build_attempt_view(
            language="ja",
            item_id=activity.activity_id,
            level=1,
            show_translation=False,
        )
        result = service.evaluate_attempt(
            PronunciationMatchAttempt(
                language="ja",
                item_id=activity.activity_id,
                expected_text=activity.prompt,
                recognized_text=activity.prompt,
                audio_duration_seconds=2.0,
                speech_seconds=1.8,
                pause_seconds=0.2,
                pitch_track_hz=[150.0, 151.0, 149.0],
                level=1,
            )
        )
        self.assertEqual(result["activity_type"], GAME_TYPE_PRONUNCIATION_MATCH)
        self.assertIn("is_match", result)
        self.assertIn("match_threshold", result)
        self.assertIn("literal_translation", result)
        self.assertEqual(result["display"]["romanized_line"], view["romanized_line"])
        self.assertTrue(result["display"]["show_literal_translation"])
        self.assertFalse(result["retry_state"]["show_literal_translation"])

    def test_alert_is_returned_on_third_retry(self) -> None:
        service = PronunciationMatchService()
        activity = service.get_activities(language="ja", level=1)[0]
        result = service.evaluate_attempt(
            PronunciationMatchAttempt(
                language="ja",
                item_id=activity.activity_id,
                expected_text=activity.prompt,
                recognized_text=activity.prompt,
                audio_duration_seconds=2.0,
                speech_seconds=1.8,
                pause_seconds=0.2,
                pitch_track_hz=[150.0, 151.0, 149.0],
                level=1,
                retry_count=3,
            )
        )
        self.assertTrue(result["alerts"])
        self.assertIn("STT/TTS", result["alerts"][0])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(PronunciationMatchService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_PRONUNCIATION_MATCH],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_PRONUNCIATION_MATCH, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
