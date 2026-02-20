import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.scheduling import LanguageScheduleConfig
from language_games.services import (
    GAME_TYPE_LISTENING_GAP_FILL,
    GameServiceRegistry,
    ListeningGapFillAttempt,
    ListeningGapFillService,
)


class ListeningGapFillServiceTests(unittest.TestCase):
    def test_beginner_japanese_shows_options_and_romanized(self) -> None:
        service = ListeningGapFillService()
        item = service.get_items(language="ja", level=1)[0]

        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=1, show_translation=False)
        self.assertTrue(view["show_kanji_line"])
        self.assertTrue(view["show_romanized_line"])
        self.assertTrue(view["show_options"])
        self.assertTrue(view["show_translation_hint"])
        self.assertFalse(view["show_literal_translation"])

    def test_intermediate_japanese_hides_options_but_keeps_romanized(self) -> None:
        service = ListeningGapFillService()
        item = service.get_items(language="ja", level=2)[0]

        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=2, show_translation=False)
        self.assertTrue(view["show_kanji_line"])
        self.assertTrue(view["show_romanized_line"])
        self.assertFalse(view["show_options"])
        self.assertFalse(view["show_translation_hint"])

    def test_advanced_japanese_shows_only_kanji(self) -> None:
        service = ListeningGapFillService()
        item = service.get_items(language="ja", level=3)[0]

        view = service.build_attempt_view(language="ja", item_id=item.item_id, level=3, show_translation=False)
        self.assertTrue(view["show_kanji_line"])
        self.assertFalse(view["show_romanized_line"])
        self.assertFalse(view["show_options"])
        self.assertFalse(view["show_translation_hint"])

    def test_translation_always_shows_after_submit_and_hides_on_retry(self) -> None:
        service = ListeningGapFillService()
        item = service.get_items(language="ja", level=1)[0]
        expected_token = item.tokens[item.gap_positions[0]]

        result_ok = service.evaluate_attempt(
            ListeningGapFillAttempt(
                language="ja",
                item_id=item.item_id,
                user_gap_tokens=[expected_token],
                level=1,
            )
        )
        result_bad = service.evaluate_attempt(
            ListeningGapFillAttempt(
                language="ja",
                item_id=item.item_id,
                user_gap_tokens=["wrong"],
                level=1,
            )
        )

        self.assertTrue(result_ok["display"]["show_literal_translation"])
        self.assertTrue(result_bad["display"]["show_literal_translation"])
        self.assertFalse(result_ok["retry_state"]["show_literal_translation"])
        self.assertFalse(result_bad["retry_state"]["show_literal_translation"])

    def test_western_language_does_not_show_kanji(self) -> None:
        service = ListeningGapFillService()
        item = service.get_items(language="en", level=1)[0]

        view = service.build_attempt_view(language="en", item_id=item.item_id, level=1, show_translation=False)
        self.assertFalse(view["show_kanji_line"])
        self.assertIsNotNone(view["base_line"])

    def test_service_is_reusable_through_registry(self) -> None:
        registry = GameServiceRegistry()
        registry.register(ListeningGapFillService())

        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
        result = orchestrator.daily_games(
            target=self._fixed_datetime(),
            game_types=[GAME_TYPE_LISTENING_GAP_FILL],
            level=1,
        )

        self.assertEqual(result.language, "ja")
        self.assertIn(GAME_TYPE_LISTENING_GAP_FILL, result.activities)

    @staticmethod
    def _fixed_datetime():
        from datetime import datetime

        return datetime(2026, 2, 15, 9, 0)


if __name__ == "__main__":
    unittest.main()
