import unittest

from language_games.services.particle_function_match_service import (
    GAME_TYPE_PARTICLE_FUNCTION_MATCH,
    ParticleFunctionMatchAttempt,
    ParticleFunctionMatchService,
)
from languages.japanese.app.focus_item_catalog import build_fallback_focus_items_for_topic


class ParticleFunctionMatchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ParticleFunctionMatchService()

    def test_build_round_uses_topic_focus_items_with_particles(self) -> None:
        focus_items = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="identity_and_plans",
            stage="basic",
            covers=("identity", "basic_sentence_roles", "time_and_routine"),
            max_items=8,
        )

        round_data = self.service.build_round(
            focus_items=focus_items,
            seed="topic:identity_and_plans:particle-function:1",
        )

        self.assertIsNotNone(round_data)
        assert round_data is not None
        self.assertEqual(round_data.prompt, "Choose the core function that best matches this Japanese particle.")
        self.assertTrue(round_data.item.script)
        self.assertTrue(round_data.item.function_label)
        self.assertTrue(round_data.item.function_explanation)
        self.assertGreaterEqual(len(round_data.options), 3)
        self.assertIn(round_data.correct_option_id, {option.option_id for option in round_data.options})
        self.assertTrue(any(option.label == round_data.item.function_label for option in round_data.options))

    def test_evaluate_attempt_marks_correct_option(self) -> None:
        result = self.service.evaluate_attempt(
            ParticleFunctionMatchAttempt(
                language="ja",
                item_id="particle-は",
                script="は",
                selected_option_id="particle-function-2",
                correct_option_id="particle-function-2",
                correct_function_label="Topic marker",
                function_explanation="Marks the topic of the sentence.",
                reading_romanized="wa",
                reading_kana="は",
                level=1,
            )
        )

        self.assertEqual(result["game_type"], GAME_TYPE_PARTICLE_FUNCTION_MATCH)
        self.assertEqual(result["score"], 100)
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["meaning"], "Topic marker")
        self.assertEqual(result["reading_romanized"], "wa")
        self.assertEqual(result["reading_kana"], "は")
        self.assertEqual(result["explanation"], "Marks the topic of the sentence.")


if __name__ == "__main__":
    unittest.main()
