import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_SENTENCE_ORDER,
    GameServiceRegistry,
    SentenceOrderAttempt,
    SentenceOrderService,
)


class SentenceOrderServiceTests(unittest.TestCase):
    def test_eastern_view_has_kanji_and_romanized(self) -> None:
        service = SentenceOrderService()
        item = service.get_items(language="ja", level=1)[0]

        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=1, show_translation=False)
        self.assertTrue(view["show_kanji_line"])
        self.assertIsNotNone(view["kanji_line"])
        self.assertIsNotNone(view["romanized_line"])
        self.assertFalse(view["show_literal_translation"])
        self.assertIsNone(view["literal_translation"])
        self.assertTrue(view["show_translation_hint"])
        self.assertIsNotNone(view["translation_hint"])

    def test_advanced_eastern_view_hides_romanized_and_hint(self) -> None:
        service = SentenceOrderService()
        item = service.get_items(language="ja", level=3)[0]

        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=3, show_translation=False)
        self.assertTrue(view["show_kanji_line"])
        self.assertFalse(view["show_romanized_line"])
        self.assertFalse(view["show_translation_hint"])

    def test_western_view_hides_kanji_line(self) -> None:
        service = SentenceOrderService()
        item = service.get_items(language="en", level=1)[0]

        view = service.build_attempt_view(language="en", item_id=item.item_id, level=1, show_translation=False)
        self.assertFalse(view["show_kanji_line"])
        self.assertIsNone(view["kanji_line"])
        self.assertIsNotNone(view["base_line"])

    def test_translation_shows_after_submit_and_hides_on_retry(self) -> None:
        service = SentenceOrderService()
        item = service.get_items(language="ja", level=1)[0]

        wrong_result = service.evaluate_attempt(
            SentenceOrderAttempt(
                language="ja",
                item_id=item.item_id,
                ordered_tokens_by_user=list(reversed(item.ordered_tokens)),
                level=1,
            )
        )
        self.assertTrue(wrong_result["display"]["show_literal_translation"])
        self.assertIsNotNone(wrong_result["display"]["literal_translation"])
        self.assertFalse(wrong_result["retry_state"]["show_literal_translation"])
        self.assertIsNone(wrong_result["retry_state"]["literal_translation"])

        good_result = service.evaluate_attempt(
            SentenceOrderAttempt(
                language="ja",
                item_id=item.item_id,
                ordered_tokens_by_user=item.ordered_tokens,
                level=1,
            )
        )
        self.assertTrue(good_result["is_correct"])
        self.assertTrue(good_result["display"]["show_literal_translation"])
        self.assertFalse(good_result["retry_state"]["show_literal_translation"])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(SentenceOrderService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_SENTENCE_ORDER],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_SENTENCE_ORDER, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
