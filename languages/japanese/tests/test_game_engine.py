from datetime import date, timedelta

from languages.japanese.app.game_engine import DailyGamePlanner, LearnerSnapshot


def test_choose_games_daily_count_and_rotation():
    planner = DailyGamePlanner()
    learner = LearnerSnapshot(
        learner_id="ana",
        streak_days=3,
        recent_accuracy=0.6,
        recent_games=["kanji_match", "kana_speed_round", "context_quiz"],
    )

    games = planner.choose_games(learner, date(2026, 1, 1))
    assert 3 <= len(games) <= 4
    assert not set(games).intersection(set(learner.recent_games))


def test_difficulty_progression():
    planner = DailyGamePlanner()
    low = LearnerSnapshot("a", streak_days=0, recent_accuracy=0.4)
    high = LearnerSnapshot("b", streak_days=20, recent_accuracy=0.9)

    assert planner.difficulty_for(low) < planner.difficulty_for(high)


def test_rotation_reset_when_not_enough_candidates():
    planner = DailyGamePlanner()
    learner = LearnerSnapshot(
        learner_id="ana",
        streak_days=1,
        recent_accuracy=0.8,
        recent_games=[
            "kanji_match",
            "kana_speed_round",
            "grammar_particle_fix",
            "sentence_order",
            "listening_gap_fill",
            "pronunciation_match",
            "shadowing_score",
            "context_quiz",
        ],
    )

    day = date(2026, 1, 1)
    games = planner.choose_games(learner, day)
    assert 3 <= len(games) <= 4

    games_next = planner.choose_games(learner, day + timedelta(days=1))
    assert games != games_next
