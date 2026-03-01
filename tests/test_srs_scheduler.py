import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from languages.japanese.app import api
from languages.japanese.app.memory import ItemReviewState, ProgressMemory
from languages.japanese.app.topic_flow import JA_TOPIC_IDENTITY_AND_PLANS


class SRSSchedulerTests(unittest.TestCase):
    def test_next_srs_state_success_sets_initial_due(self) -> None:
        interval, ease, repetitions, lapses, quality = api._next_srs_state(previous=None, score=95)

        self.assertEqual(interval, 1)
        self.assertEqual(repetitions, 1)
        self.assertEqual(lapses, 0)
        self.assertEqual(quality, 5)
        self.assertGreaterEqual(ease, api.SRS_DEFAULT_EASE)

    def test_next_srs_state_failure_resets_repetitions(self) -> None:
        previous = ItemReviewState(
            learner_id="learner",
            language="ja",
            topic_key="identity_and_plans",
            game_type="sentence_order",
            item_id="ja-sentence-order-1-1",
            due_day_iso=date.today().isoformat(),
            interval_days=3,
            ease=2.6,
            repetitions=2,
            lapses=0,
            last_score=100,
            last_seen_day_iso=date.today().isoformat(),
        )

        interval, ease, repetitions, lapses, quality = api._next_srs_state(previous=previous, score=40)

        self.assertEqual(quality, 1)
        self.assertEqual(interval, 1)
        self.assertEqual(repetitions, 0)
        self.assertEqual(lapses, 1)
        self.assertLess(ease, previous.ease)

    def test_next_srs_state_caps_interval_for_very_large_previous_state(self) -> None:
        previous = ItemReviewState(
            learner_id="learner",
            language="ja",
            topic_key="identity_and_plans",
            game_type="sentence_order",
            item_id="ja-sentence-order-1-1",
            due_day_iso=date.today().isoformat(),
            interval_days=10_000_000,
            ease=3.8,
            repetitions=20,
            lapses=0,
            last_score=100,
            last_seen_day_iso=date.today().isoformat(),
        )

        interval, _, repetitions, _, quality = api._next_srs_state(previous=previous, score=100)
        self.assertEqual(quality, 5)
        self.assertEqual(repetitions, 21)
        self.assertLessEqual(interval, api.SRS_MAX_INTERVAL_DAYS)

    def test_update_item_review_state_applies_success_then_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = ProgressMemory(f"{tmp_dir}/srs.db")
            learner_id = f"srs-update-{uuid4().hex}"
            today_iso = date.today().isoformat()

            with patch.object(api, "memory", memory):
                api._update_item_review_state(
                    learner_id=learner_id,
                    language="ja",
                    game_type="sentence_order",
                    item_id="ja-sentence-order-1-1",
                    payload={"topic_key": "identity_and_plans"},
                    score=100,
                )

                first_state = memory.load_item_review_state(
                    learner_id=learner_id,
                    language="ja",
                    topic_key="identity_and_plans",
                    game_type="sentence_order",
                    item_id="ja-sentence-order-1-1",
                )
                self.assertIsNotNone(first_state)
                self.assertEqual(first_state.repetitions, 1)
                self.assertEqual(first_state.lapses, 0)
                self.assertEqual(
                    first_state.due_day_iso,
                    (date.fromisoformat(today_iso) + timedelta(days=1)).isoformat(),
                )

                api._update_item_review_state(
                    learner_id=learner_id,
                    language="ja",
                    game_type="sentence_order",
                    item_id="ja-sentence-order-1-1",
                    payload={"topic_key": "identity_and_plans"},
                    score=35,
                )

                second_state = memory.load_item_review_state(
                    learner_id=learner_id,
                    language="ja",
                    topic_key="identity_and_plans",
                    game_type="sentence_order",
                    item_id="ja-sentence-order-1-1",
                )
                self.assertIsNotNone(second_state)
                self.assertEqual(second_state.repetitions, 0)
                self.assertGreaterEqual(second_state.lapses, 1)
                self.assertEqual(
                    second_state.due_day_iso,
                    (date.fromisoformat(today_iso) + timedelta(days=1)).isoformat(),
                )

    def test_due_item_listing_filters_and_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = ProgressMemory(f"{tmp_dir}/srs.db")
            learner_id = f"srs-due-{uuid4().hex}"
            today_iso = date.today().isoformat()

            memory.upsert_item_review_state(
                learner_id=learner_id,
                language="ja",
                topic_key="identity_and_plans",
                game_type="sentence_order",
                item_id="ja-sentence-order-1-1",
                due_day_iso=(date.today() - timedelta(days=1)).isoformat(),
                interval_days=1,
                ease=2.5,
                repetitions=1,
                lapses=0,
                last_score=90,
                last_seen_day_iso=today_iso,
            )
            memory.upsert_item_review_state(
                learner_id=learner_id,
                language="ja",
                topic_key="identity_and_plans",
                game_type="listening_gap_fill",
                item_id="ja-gap-1-1",
                due_day_iso=today_iso,
                interval_days=2,
                ease=2.3,
                repetitions=2,
                lapses=1,
                last_score=70,
                last_seen_day_iso=today_iso,
            )
            memory.upsert_item_review_state(
                learner_id=learner_id,
                language="ja",
                topic_key="identity_and_plans",
                game_type="mora_romanization",
                item_id="ja-mora-romanization-1-1",
                due_day_iso=(date.today() + timedelta(days=2)).isoformat(),
                interval_days=3,
                ease=2.1,
                repetitions=3,
                lapses=2,
                last_score=60,
                last_seen_day_iso=today_iso,
            )

            due_items = memory.list_due_item_review_states(
                learner_id=learner_id,
                language="ja",
                current_day_iso=today_iso,
                limit=10,
            )

            self.assertEqual(len(due_items), 2)
            self.assertEqual(due_items[0].item_id, "ja-sentence-order-1-1")
            self.assertEqual(due_items[1].item_id, "ja-gap-1-1")

    def test_weekly_exam_questions_prioritize_closed_due_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = ProgressMemory(f"{tmp_dir}/srs.db")
            learner_id = f"srs-weekly-{uuid4().hex}"
            today_iso = date.today().isoformat()

            memory.mark_topic_closed(
                learner_id=learner_id,
                language="ja",
                topic_key="identity_and_plans",
                closed_day_iso=today_iso,
                closed_level=2,
                reason="test_weekly_closed_due",
            )
            memory.upsert_item_review_state(
                learner_id=learner_id,
                language="ja",
                topic_key="identity_and_plans",
                game_type="grammar_particle_fix",
                item_id="ja-particle-2-1",
                due_day_iso=today_iso,
                interval_days=3,
                ease=2.4,
                repetitions=2,
                lapses=1,
                last_score=62,
                last_seen_day_iso=today_iso,
            )

            with patch.object(api, "memory", memory):
                questions = api._weekly_exam_questions(
                    learner_id=learner_id,
                    language="ja",
                    current_topic=JA_TOPIC_IDENTITY_AND_PLANS,
                    current_level=1,
                    today_iso=today_iso,
                    question_count=5,
                )

            self.assertGreaterEqual(len(questions), 3)
            self.assertEqual(questions[0]["source"], "closed_due")
            self.assertEqual(questions[0]["game_type"], "grammar_particle_fix")
            self.assertEqual(questions[0]["item_id"], "ja-particle-2-1")


if __name__ == "__main__":
    unittest.main()
