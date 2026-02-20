import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_GRAMMAR_PARTICLE_FIX,
    GameServiceRegistry,
    GrammarParticleAttempt,
    GrammarParticleFixService,
)


class GrammarParticleFixServiceTests(unittest.TestCase):
    def test_japanese_activities_are_available(self) -> None:
        service = GrammarParticleFixService()
        activities = service.get_activities(language="ja", level=1)
        self.assertTrue(activities)
        self.assertEqual(activities[0].game_type, GAME_TYPE_GRAMMAR_PARTICLE_FIX)

    def test_non_supported_language_returns_empty(self) -> None:
        service = GrammarParticleFixService()
        self.assertEqual(service.get_activities(language="en", level=1), [])

    def test_evaluate_attempt_correct_and_incorrect(self) -> None:
        service = GrammarParticleFixService()
        item = service.get_items(language="ja", level=1)[0]

        correct = service.evaluate_attempt(
            GrammarParticleAttempt(
                language="ja",
                item_id=item.item_id,
                selected_particle=item.correct_particle,
                level=1,
            )
        )
        incorrect = service.evaluate_attempt(
            GrammarParticleAttempt(
                language="ja",
                item_id=item.item_id,
                selected_particle="を" if item.correct_particle != "を" else "に",
                level=1,
            )
        )

        self.assertTrue(correct["is_correct"])
        self.assertEqual(correct["score"], 100)
        self.assertIn("literal_translation", correct)
        self.assertTrue(correct["literal_translation"])
        self.assertFalse(incorrect["is_correct"])
        self.assertEqual(incorrect["score"], 0)
        self.assertTrue(correct["display"]["show_literal_translation"])
        self.assertFalse(correct["retry_state"]["show_literal_translation"])

    def test_beginner_view_shows_romanized_and_translation_hint(self) -> None:
        service = GrammarParticleFixService()
        item = service.get_items(language="ja", level=1)[0]
        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=1, show_translation=False)
        self.assertTrue(view["show_romanized_line"])
        self.assertTrue(view["show_translation_hint"])

    def test_advanced_view_hides_romanized_and_translation_hint(self) -> None:
        service = GrammarParticleFixService()
        item = service.get_items(language="ja", level=3)[0]
        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=3, show_translation=False)
        self.assertFalse(view["show_romanized_line"])
        self.assertFalse(view["show_translation_hint"])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(GrammarParticleFixService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_GRAMMAR_PARTICLE_FIX],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_GRAMMAR_PARTICLE_FIX, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
