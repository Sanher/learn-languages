import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_MORA_ROMANIZATION,
    GameServiceRegistry,
    MoraRomanizationAttempt,
    MoraRomanizationService,
)


class MoraRomanizationServiceTests(unittest.TestCase):
    def test_beginner_activity_shows_mora_and_romaji(self) -> None:
        service = MoraRomanizationService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        prompt = activities[0].prompt
        self.assertIn("Mora (kana):", prompt)
        self.assertIn("Mora (romaji):", prompt)

    def test_advanced_activity_hides_mora_romaji_and_shows_plain_japanese(self) -> None:
        service = MoraRomanizationService()
        activities = service.get_activities(language="ja", level=2)
        self.assertTrue(activities)
        prompt = activities[0].prompt
        self.assertNotIn("Mora (romaji):", prompt)
        self.assertIn("Japanese text:", prompt)

    def test_beginner_shows_kanji_after_submit_even_if_incorrect(self) -> None:
        service = MoraRomanizationService()
        item = service.get_items(language="ja", level=1)[0]
        result = service.evaluate_attempt(
            MoraRomanizationAttempt(
                language="ja",
                item_id=item.item_id,
                user_romanized_text="watashiwagakuseidesu",
                level=1,
            )
        )
        self.assertIn("kanji_mora_line", result)
        self.assertTrue(result["kanji_mora_line"])

    def test_advanced_shows_kanji_only_when_correct(self) -> None:
        service = MoraRomanizationService()
        item = service.get_items(language="ja", level=2)[0]
        wrong = service.evaluate_attempt(
            MoraRomanizationAttempt(
                language="ja",
                item_id=item.item_id,
                user_romanized_text="kyouwasushiotabemasu",
                level=2,
            )
        )
        correct = service.evaluate_attempt(
            MoraRomanizationAttempt(
                language="ja",
                item_id=item.item_id,
                user_romanized_text="kyou wa sushi o tabemasu",
                level=2,
            )
        )
        self.assertFalse(wrong["is_correct"])
        self.assertIsNone(wrong["kanji_mora_line"])
        self.assertTrue(correct["is_correct"])
        self.assertTrue(correct["kanji_mora_line"])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(MoraRomanizationService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_MORA_ROMANIZATION],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_MORA_ROMANIZATION, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
