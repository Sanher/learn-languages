from datetime import date, timedelta
import unittest

from languages.japanese.app.game_engine import DailyGamePlanner, LearnerSnapshot


class ContextQuizFrequencyPolicyTests(unittest.TestCase):
    def test_context_quiz_appears_less_with_progress(self) -> None:
        planner = DailyGamePlanner(game_pool=["kanji_match", "context_quiz", "shadowing_score"])
        low = LearnerSnapshot(learner_id="ana", streak_days=1, recent_accuracy=0.45, recent_games=[])
        high = LearnerSnapshot(learner_id="ana", streak_days=40, recent_accuracy=0.95, recent_games=[])

        start = date(2026, 1, 1)
        low_count = 0
        high_count = 0
        total_days = 28

        for offset in range(total_days):
            day = start + timedelta(days=offset)
            if "context_quiz" in planner.choose_games(low, day):
                low_count += 1
            if "context_quiz" in planner.choose_games(high, day):
                high_count += 1

        self.assertGreater(low_count, high_count)


if __name__ == "__main__":
    unittest.main()
