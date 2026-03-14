import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_KANJI_MATCH,
    GameServiceRegistry,
    KanjiMatchAttempt,
    KanjiMatchService,
)


class KanjiMatchServiceTests(unittest.TestCase):
    def test_japanese_activities_are_available(self) -> None:
        service = KanjiMatchService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_KANJI_MATCH)
        self.assertIn("Readings (romaji)", activities[0].prompt)
        self.assertIn("Meaning bank", activities[0].prompt)

    def test_advanced_activity_hides_romaji_but_keeps_meaning_bank(self) -> None:
        service = KanjiMatchService()
        activities = service.get_activities(language="ja", level=3)
        self.assertTrue(activities)
        self.assertNotIn("Readings (romaji)", activities[0].prompt)
        self.assertIn("Meaning bank", activities[0].prompt)

    def test_western_language_is_not_eligible(self) -> None:
        service = KanjiMatchService()
        self.assertFalse(service.is_language_eligible("en"))
        activities = service.get_activities(language="en", level=1)
        self.assertEqual(activities, [])

    def test_evaluate_attempt(self) -> None:
        service = KanjiMatchService()
        expected_pairs = service.get_pairs(language="ja", level=1)[:3]
        result = service.evaluate_attempt(
            KanjiMatchAttempt(
                language="ja",
                expected_pairs=expected_pairs,
                learner_matches={
                    expected_pairs[0].symbol: expected_pairs[0].meaning,
                    expected_pairs[1].symbol: "incorrect",
                    expected_pairs[2].symbol: expected_pairs[2].meaning,
                },
                level=1,
            )
        )

        self.assertIn("score", result)
        self.assertEqual(result["accuracy"], 0.67)
        self.assertEqual(len(result["mistakes"]), 1)
        self.assertTrue(result["display"]["show_literal_translation"])
        self.assertFalse(result["retry_state"]["show_literal_translation"])

    def test_evaluate_readings_with_drag_mode(self) -> None:
        service = KanjiMatchService()
        expected_pairs = service.get_pairs(language="ja", level=1)[:2]
        result = service.evaluate_attempt(
            KanjiMatchAttempt(
                language="ja",
                expected_pairs=expected_pairs,
                learner_readings={
                    expected_pairs[0].symbol: expected_pairs[0].reading_romaji,
                    expected_pairs[1].symbol: "wrong romaji",
                },
                level=1,
            )
        )

        self.assertEqual(result["reading_accuracy"], 0.5)
        self.assertEqual(result["score"], 50)
        self.assertFalse(result["require_meaning_input"])
        self.assertEqual(len(result["reading_results"]), 2)

    def test_advanced_mode_keeps_reading_only_scoring(self) -> None:
        service = KanjiMatchService()
        expected_pairs = service.get_pairs(language="ja", level=2)[2:4]
        result = service.evaluate_attempt(
            KanjiMatchAttempt(
                language="ja",
                expected_pairs=expected_pairs,
                learner_readings={
                    expected_pairs[0].symbol: expected_pairs[0].reading_romaji,
                    expected_pairs[1].symbol: expected_pairs[1].reading_romaji,
                },
                level=2,
            )
        )

        self.assertFalse(result["require_meaning_input"])
        self.assertEqual(result["reading_accuracy"], 1.0)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["meaning_results"], [])

    def test_attempt_view_exposes_kana_and_hides_meaning_input(self) -> None:
        service = KanjiMatchService()
        view = service.build_attempt_view(language="ja", level=2)

        self.assertFalse(view["require_meaning_input"])
        self.assertIn("学", view["reading_kana"])
        self.assertTrue(view["reading_kana"]["学"])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(KanjiMatchService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_KANJI_MATCH],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_KANJI_MATCH, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
