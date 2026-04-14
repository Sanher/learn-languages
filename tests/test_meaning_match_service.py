import unittest

from language_games.services.meaning_match_service import (
    GAME_TYPE_MEANING_MATCH,
    MeaningMatchAttempt,
    MeaningMatchService,
)
from languages.japanese.app.focus_item_catalog import build_fallback_focus_items_for_topic


class MeaningMatchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MeaningMatchService()

    def test_build_round_uses_topic_focus_items_with_meanings(self) -> None:
        focus_items = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="basic_greetings",
            stage="basic",
            covers=("identity", "basic_questions"),
        )

        round_data = self.service.build_round(
            focus_items=focus_items,
            seed="topic:basic_greetings:1",
        )

        self.assertIsNotNone(round_data)
        assert round_data is not None
        self.assertEqual(round_data.prompt, "Choose the correct English meaning for this Japanese item.")
        self.assertTrue(round_data.item.script)
        self.assertTrue(round_data.item.meaning)
        self.assertGreaterEqual(len(round_data.options), 3)
        self.assertIn(round_data.correct_option_id, {option.option_id for option in round_data.options})
        self.assertTrue(any(option.meaning == round_data.item.meaning for option in round_data.options))

    def test_evaluate_attempt_marks_correct_option(self) -> None:
        result = self.service.evaluate_attempt(
            MeaningMatchAttempt(
                language="ja",
                item_id="word-明日",
                script="明日",
                selected_option_id="meaning-1",
                correct_option_id="meaning-1",
                correct_meaning="tomorrow",
                reading_romanized="ashita",
                reading_kana="あした",
                level=1,
            )
        )

        self.assertEqual(result["game_type"], GAME_TYPE_MEANING_MATCH)
        self.assertEqual(result["score"], 100)
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["correct_meaning"], "tomorrow")
        self.assertEqual(result["reading_romanized"], "ashita")
        self.assertEqual(result["reading_kana"], "あした")


if __name__ == "__main__":
    unittest.main()
