import unittest

from language_games.services.kanji_reading_match_service import (
    GAME_TYPE_KANJI_READING_MATCH,
    KanjiReadingMatchAttempt,
    KanjiReadingMatchService,
)
from languages.japanese.app.focus_item_catalog import build_fallback_focus_items_for_topic


class KanjiReadingMatchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = KanjiReadingMatchService()

    def test_build_round_uses_topic_focus_items_with_kanji(self) -> None:
        focus_items = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="identity_and_plans",
            stage="basic",
            covers=("identity", "basic_sentence_roles", "time_and_routine"),
        )

        round_data = self.service.build_round(
            focus_items=focus_items,
            seed="topic:identity_and_plans:1",
        )

        self.assertIsNotNone(round_data)
        assert round_data is not None
        self.assertEqual(round_data.prompt, "Choose the correct romanized reading for this kanji or word.")
        self.assertTrue(round_data.item.script)
        self.assertTrue(round_data.item.reading_romanized)
        self.assertGreaterEqual(len(round_data.options), 3)
        self.assertIn(round_data.correct_option_id, {option.option_id for option in round_data.options})
        self.assertTrue(any(option.reading_romanized == round_data.item.reading_romanized for option in round_data.options))

    def test_evaluate_attempt_marks_correct_option(self) -> None:
        result = self.service.evaluate_attempt(
            KanjiReadingMatchAttempt(
                language="ja",
                item_id="word-今日",
                script="今日",
                selected_option_id="reading-2",
                correct_option_id="reading-2",
                correct_reading_romanized="kyou",
                correct_reading_kana="きょう",
                meaning="today",
                level=1,
            )
        )

        self.assertEqual(result["game_type"], GAME_TYPE_KANJI_READING_MATCH)
        self.assertEqual(result["score"], 100)
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["correct_reading"], "kyou")
        self.assertEqual(result["correct_reading_kana"], "きょう")
        self.assertEqual(result["meaning"], "today")


if __name__ == "__main__":
    unittest.main()
