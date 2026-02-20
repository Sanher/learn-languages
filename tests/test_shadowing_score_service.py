import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_SHADOWING_SCORE,
    ShadowingAttempt,
    ShadowingScoreService,
    GameServiceRegistry,
)


class ShadowingScoreServiceTests(unittest.TestCase):
    def test_japanese_activities_are_available(self) -> None:
        service = ShadowingScoreService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_SHADOWING_SCORE)

    def test_beginner_and_intermediate_show_romanized(self) -> None:
        service = ShadowingScoreService()
        beginner_activity = service.get_activities(language="ja", level=1)[0]
        intermediate_activity = service.get_activities(language="ja", level=2)[0]

        beginner_view = service.build_attempt_view(
            language="ja",
            item_id=beginner_activity.activity_id,
            level=1,
        )
        intermediate_view = service.build_attempt_view(
            language="ja",
            item_id=intermediate_activity.activity_id,
            level=2,
        )
        self.assertTrue(beginner_view["show_romanized_line"])
        self.assertTrue(intermediate_view["show_romanized_line"])
        self.assertTrue(beginner_view["romanized_line"])
        self.assertTrue(intermediate_view["romanized_line"])

    def test_advanced_hides_romanized(self) -> None:
        service = ShadowingScoreService()
        activity = service.get_activities(language="ja", level=3)[0]
        view = service.build_attempt_view(
            language="ja",
            item_id=activity.activity_id,
            level=3,
        )
        self.assertFalse(view["show_romanized_line"])
        self.assertIsNone(view["romanized_line"])

    def test_non_supported_language_returns_empty_activities(self) -> None:
        service = ShadowingScoreService()
        activities = service.get_activities(language="en", level=1)
        self.assertEqual(activities, [])

    def test_evaluate_attempt_japanese(self) -> None:
        service = ShadowingScoreService()
        result = service.evaluate_attempt(
            ShadowingAttempt(
                language="ja",
                expected_text="ありがとうございます",
                learner_text="ありがとございます",
                audio_duration_seconds=2.4,
                pause_seconds=0.2,
                level=1,
            )
        )
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertIn("metrics", result)
        self.assertIn("feedback", result)

    def test_alert_is_returned_on_third_retry(self) -> None:
        service = ShadowingScoreService()
        result = service.evaluate_attempt(
            ShadowingAttempt(
                language="ja",
                expected_text="ありがとうございます",
                learner_text="ありがとうございます",
                audio_duration_seconds=2.4,
                pause_seconds=0.2,
                level=1,
                retry_count=3,
            )
        )
        self.assertTrue(result["alerts"])
        self.assertIn("STT/TTS", result["alerts"][0])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(ShadowingScoreService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_SHADOWING_SCORE],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_SHADOWING_SCORE, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
