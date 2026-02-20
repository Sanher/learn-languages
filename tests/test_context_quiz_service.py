import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_CONTEXT_QUIZ,
    ContextQuizAttempt,
    ContextQuizService,
    GameServiceRegistry,
)


class ContextQuizServiceTests(unittest.TestCase):
    def test_japanese_activities_are_available(self) -> None:
        service = ContextQuizService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_CONTEXT_QUIZ)
        self.assertNotIn("Target sentence:", activities[0].prompt)
        self.assertNotIn("Options:", activities[0].prompt)

    def test_evaluate_attempt_shows_translation_and_retry_hides_it(self) -> None:
        service = ContextQuizService()
        item = service.get_items(language="ja", level=1)[0]
        correct_option = next(option for option in item.options if option.is_correct)

        result = service.evaluate_attempt(
            ContextQuizAttempt(
                language="ja",
                item_id=item.item_id,
                selected_option_id=correct_option.option_id,
                level=1,
            )
        )

        self.assertTrue(result["is_correct"])
        self.assertTrue(result["display"]["show_literal_translation"])
        self.assertFalse(result["retry_state"]["show_literal_translation"])

    def test_advanced_level_hides_romanized_hint(self) -> None:
        service = ContextQuizService()
        activities = service.get_activities(language="ja", level=3)
        self.assertTrue(activities)
        self.assertNotIn("Romanized:", activities[0].prompt)

    def test_ui_options_include_romaji_for_japanese(self) -> None:
        service = ContextQuizService()
        item = service.get_items(language="ja", level=1)[0]
        options = service.options_for_ui(item.options)
        self.assertTrue(options)
        self.assertIn("romaji", options[0])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(ContextQuizService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_CONTEXT_QUIZ],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_CONTEXT_QUIZ, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
