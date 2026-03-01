import unittest
import unittest.mock
from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from languages.japanese.app import api
from languages.japanese.app.api import app


MORA_EXPECTED_TEXT_BY_ITEM = {
    "ja-mora-romanization-1-1": "watashi wa gakusei desu",
    "ja-mora-romanization-2-1": "kyou wa sushi o tabemasu",
    "ja-mora-romanization-3-1": "ashita tomodachi to eiga o mimasu",
}


class TopicDailyFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.learner_id = f"topic-flow-{uuid4().hex}"

    def test_daily_response_contains_lesson_and_three_topic_games(self) -> None:
        response = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("topic", data)
        self.assertIn("lesson", data)
        self.assertIn("daily_progress", data)
        self.assertEqual(len(data.get("daily_games", [])), 3)
        self.assertGreaterEqual(len(data.get("extra_games", [])), 1)
        self.assertTrue(all(bool(card.get("deferred_load")) for card in data.get("extra_games", [])))
        self.assertFalse(data["daily_progress"]["lesson_completed"])
        self.assertEqual(data["daily_progress"]["daily_score"], 0)
        self.assertEqual(data["daily_progress"]["daily_score_max"], 300)
        self.assertEqual(data["daily_progress"]["topic_days_count"], 1)
        self.assertEqual(data["daily_progress"]["topic_day_target_score"], 150)
        self.assertEqual(data["daily_progress"]["high_score_days_over_240"], 0)
        self.assertEqual(data["daily_progress"]["closed_topics_count"], 0)
        self.assertIsNone(data.get("selected_game"))

    def test_lesson_plus_three_daily_games_unlocks_extras(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        lesson = daily_data["lesson"]

        complete_lesson = self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": lesson["topic_key"],
            },
        )
        self.assertEqual(complete_lesson.status_code, 200)
        self.assertTrue(complete_lesson.json()["daily_progress"]["lesson_completed"])

        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            evaluation = self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )
            self.assertEqual(evaluation.status_code, 200)
            self.assertNotIn("error", evaluation.json())

        after = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(after.status_code, 200)
        after_data = after.json()
        self.assertTrue(after_data["daily_progress"]["extras_unlocked"])
        self.assertGreaterEqual(len(after_data.get("available_games", [])), 6)
        self.assertEqual(after_data["daily_progress"]["daily_score"], 300)
        self.assertEqual(after_data["daily_progress"]["daily_score_max"], 300)

    def test_level_override_cannot_increase(self) -> None:
        response = self.client.post(
            "/api/games/daily",
            json={
                "learner_id": self.learner_id,
                "level_override_today": 3,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("level_up_blocked"))
        self.assertEqual(data.get("today_level"), data.get("current_level"))

    def test_level_override_is_disabled_even_when_lowering(self) -> None:
        api.memory.set_language_level(self.learner_id, "ja", 3)

        high = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(high.status_code, 200)
        high_data = high.json()
        self.assertEqual(high_data["today_level"], 3)

        lowered = self.client.post(
            "/api/games/daily",
            json={
                "learner_id": self.learner_id,
                "level_override_today": 2,
            },
        )
        self.assertEqual(lowered.status_code, 200)
        lowered_data = lowered.json()
        self.assertTrue(lowered_data["level_up_blocked"])
        self.assertEqual(lowered_data["today_level"], 3)
        self.assertEqual(high_data["topic"]["topic_key"], lowered_data["topic"]["topic_key"])
        self.assertEqual(high_data["lesson"]["title"], lowered_data["lesson"]["title"])

    def test_extra_game_load_is_deferred_and_returns_full_card(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": daily_data["lesson"]["topic_key"],
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        unlocked = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(unlocked.status_code, 200)
        unlocked_data = unlocked.json()
        self.assertTrue(unlocked_data["daily_progress"]["extras_unlocked"])
        extra_meta = unlocked_data["extra_games"][0]

        load = self.client.post(
            "/api/games/extra/load",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": unlocked_data["topic"]["topic_key"],
                "game_type": extra_meta["game_type"],
            },
        )
        self.assertEqual(load.status_code, 200)
        load_data = load.json()
        self.assertIn("card", load_data)
        card = load_data["card"]
        self.assertEqual(card["game_type"], extra_meta["game_type"])
        self.assertTrue(card.get("prompt"))
        self.assertIn("ai_generated_prompt", card)
        self.assertIn("ai_prompt_source", card)

    def test_extra_game_load_includes_translation_bundles_when_secondary_enabled(self) -> None:
        self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": self.learner_id,
                "secondary_language": "es",
            },
        )
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": daily_data["lesson"]["topic_key"],
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        unlocked = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(unlocked.status_code, 200)
        extra_meta = unlocked.json()["extra_games"][0]

        load = self.client.post(
            "/api/games/extra/load",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": unlocked.json()["topic"]["topic_key"],
                "game_type": extra_meta["game_type"],
            },
        )
        self.assertEqual(load.status_code, 200)
        card = load.json()["card"]
        self.assertIn("prompt_translations", card)
        self.assertEqual(card["prompt_translations"]["en"], card["prompt"])
        self.assertEqual(card["prompt_translations"]["secondary_lang"], "es")
        self.assertIn("ai_generated_prompt_translations", card)
        self.assertEqual(card["ai_generated_prompt_translations"]["secondary_lang"], "es")

    def test_playing_extra_game_does_not_change_daily_score(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": daily_data["lesson"]["topic_key"],
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        unlocked = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(unlocked.status_code, 200)
        unlocked_data = unlocked.json()
        score_before = unlocked_data["daily_progress"]["daily_score"]
        self.assertEqual(score_before, 300)

        extra_load = self.client.post(
            "/api/games/extra/load",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": unlocked_data["topic"]["topic_key"],
                "game_type": "grammar_particle_fix",
            },
        )
        self.assertEqual(extra_load.status_code, 200)
        extra_card = extra_load.json()["card"]

        extra_payload = {
            "item_id": extra_card["activity_id"],
            "selected_particle": (extra_card.get("payload", {}).get("options") or ["は"])[0],
        }
        evaluated = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": extra_card["game_type"],
                "language": extra_card["language"],
                "level": extra_card["level"],
                "retry_count": 0,
                "payload": extra_payload,
            },
        )
        self.assertEqual(evaluated.status_code, 200)
        self.assertNotIn("error", evaluated.json())

        after = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(after.status_code, 200)
        after_data = after.json()
        self.assertEqual(after_data["daily_progress"]["daily_score"], score_before)

    def test_extra_game_prefers_due_item_from_closed_topic(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        today_iso = date.today().isoformat()
        api.memory.mark_topic_closed(
            learner_id=self.learner_id,
            language="ja",
            topic_key=topic_key,
            closed_day_iso=today_iso,
            closed_level=2,
            reason="test_due_priority",
        )
        api.memory.upsert_item_review_state(
            learner_id=self.learner_id,
            language="ja",
            topic_key=topic_key,
            game_type="grammar_particle_fix",
            item_id="ja-particle-2-1",
            due_day_iso=today_iso,
            interval_days=2,
            ease=2.4,
            repetitions=2,
            lapses=1,
            last_score=56,
            last_seen_day_iso=today_iso,
        )

        extra = self.client.post(
            "/api/games/extra/load",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
                "game_type": "grammar_particle_fix",
            },
        )
        self.assertEqual(extra.status_code, 200)
        card = extra.json()["card"]
        self.assertEqual(card["activity_id"], "ja-particle-2-1")
        self.assertEqual(card.get("selection_source"), "due_closed_topic")
        self.assertEqual(card.get("topic_key"), topic_key)

    def test_weekly_exam_cumulative_phase_one_returns_questions_without_marking_result(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        before_state = api.memory.load_or_create_assessment_state(self.learner_id)
        self.assertEqual(before_state.weekly_exam_passed_count, 0)
        self.assertFalse(before_state.weekly_exam_last_day_iso)

        with unittest.mock.patch.object(api, "WEEKLY_EXAM_FORCE_LEGACY", False):
            weekly_exam = self.client.post(
                "/api/exams/weekly",
                json={
                    "learner_id": self.learner_id,
                    "language": "ja",
                    "topic_key": topic_key,
                    "question_count": 6,
                },
            )

        self.assertEqual(weekly_exam.status_code, 200)
        weekly_data = weekly_exam.json()
        self.assertTrue(weekly_data["requires_answers"])
        self.assertFalse(weekly_data.get("legacy_mode", True))
        self.assertGreaterEqual(weekly_data["question_count"], 3)
        self.assertGreaterEqual(len(weekly_data.get("questions", [])), 3)

        after_state = api.memory.load_or_create_assessment_state(self.learner_id)
        self.assertEqual(after_state.weekly_exam_passed_count, 0)
        self.assertFalse(after_state.weekly_exam_last_day_iso)

    def test_weekly_exam_mode_override_forces_cumulative_flow(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        with unittest.mock.patch.object(api, "WEEKLY_EXAM_FORCE_LEGACY", True):
            weekly_exam = self.client.post(
                "/api/exams/weekly",
                json={
                    "learner_id": self.learner_id,
                    "language": "ja",
                    "topic_key": topic_key,
                    "mode": "cumulative",
                    "question_count": 6,
                },
            )

        self.assertEqual(weekly_exam.status_code, 200)
        weekly_data = weekly_exam.json()
        self.assertTrue(weekly_data["requires_answers"])
        self.assertFalse(weekly_data.get("legacy_mode", True))
        self.assertGreaterEqual(weekly_data["question_count"], 3)
        self.assertGreaterEqual(len(weekly_data.get("questions", [])), 3)

    def test_daily_score_stays_capped_at_300_after_duplicate_daily_evaluations(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": daily_data["lesson"]["topic_key"],
            },
        )

        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": card["language"],
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        first_card = daily_data["daily_games"][0]
        first_payload = self._payload_for_daily_card(first_card)
        repeat_eval = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": first_card["game_type"],
                "language": first_card["language"],
                "level": first_card["level"],
                "retry_count": 0,
                "payload": first_payload,
            },
        )
        self.assertEqual(repeat_eval.status_code, 200)

        after = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(after.status_code, 200)
        daily_progress = after.json()["daily_progress"]
        self.assertEqual(daily_progress["daily_score"], 300)
        self.assertLessEqual(daily_progress["daily_score"], daily_progress["daily_score_max"])


    def test_wrong_daily_attempt_increments_topic_failure_totals(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": daily_data["lesson"]["topic_key"],
            },
        )
        sentence_card = next(card for card in daily_data["daily_games"] if card["game_type"] == "sentence_order")
        bad_payload = {
            "item_id": sentence_card["activity_id"],
            "ordered_tokens_by_user": ["x", "y", "z"],
        }
        evaluation = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": sentence_card["game_type"],
                "language": "ja",
                "level": sentence_card["level"],
                "retry_count": 0,
                "payload": bad_payload,
            },
        )
        self.assertEqual(evaluation.status_code, 200)
        eval_data = evaluation.json()
        self.assertIn("daily_progress", eval_data)
        failures = eval_data["daily_progress"]["topic_failure_totals"]
        self.assertGreaterEqual(int(failures.get("sentence_order", 0)), 1)

    def test_weekly_exam_and_level_exam_flow(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["lesson"]["topic_key"]

        self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": "ja",
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )

        weekly_exam = self.client.post(
            "/api/exams/weekly",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(weekly_exam.status_code, 200)
        weekly_data = weekly_exam.json()
        self.assertTrue(weekly_data["passed"])
        self.assertEqual(weekly_data["daily_progress"]["weekly_exam_passed_count"], 1)

        level_exam = self.client.post(
            "/api/exams/level",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "target_level": 2,
            },
        )
        self.assertEqual(level_exam.status_code, 200)
        level_data = level_exam.json()
        self.assertTrue(level_data["passed"])
        self.assertTrue(level_data["promoted"])
        self.assertEqual(level_data["current_level"], 2)
        self.assertEqual(level_data["daily_progress"]["level_state"], level_data["current_level"])

        closed_topics = self.client.post(
            "/api/topics/closed",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
            },
        )
        self.assertEqual(closed_topics.status_code, 200)
        closed_data = closed_topics.json()
        self.assertGreaterEqual(closed_data["closed_topics_count"], 1)
        self.assertEqual(closed_data["closed_topics"][0]["topic_key"], topic_key)

    def test_topic_review_endpoint_requires_closed_topic(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        topic_key = daily.json()["topic"]["topic_key"]

        review = self.client.post(
            "/api/topics/review",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(review.status_code, 200)
        self.assertIn("error", review.json())

    def test_topic_review_endpoint_returns_review_games(self) -> None:
        topic_key = self._close_topic_and_promote_to_level_2()

        review = self.client.post(
            "/api/topics/review",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(review.status_code, 200)
        data = review.json()
        self.assertTrue(data.get("review_mode"))
        self.assertEqual(data["topic"]["topic_key"], topic_key)
        self.assertGreaterEqual(len(data.get("review_games", [])), 3)
        self.assertIsNotNone(data.get("selected_game"))

    def test_topic_review_includes_translation_bundles_when_secondary_enabled(self) -> None:
        self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": self.learner_id,
                "secondary_language": "es",
            },
        )
        topic_key = self._close_topic_and_promote_to_level_2()

        review = self.client.post(
            "/api/topics/review",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(review.status_code, 200)
        data = review.json()
        self.assertIn("title_translations", data["topic"])
        self.assertEqual(data["topic"]["title_translations"]["secondary_lang"], "es")
        self.assertIn("description_translations", data["topic"])
        self.assertEqual(data["topic"]["description_translations"]["secondary_lang"], "es")
        self.assertIn("objective_translations", data["lesson"])
        self.assertEqual(data["lesson"]["objective_translations"]["secondary_lang"], "es")
        first_card = data["review_games"][0]
        self.assertIn("prompt_translations", first_card)
        self.assertEqual(first_card["prompt_translations"]["secondary_lang"], "es")

    def test_topic_review_evaluate_does_not_modify_daily_progress(self) -> None:
        topic_key = self._close_topic_and_promote_to_level_2()
        daily_before = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily_before.status_code, 200)
        before_data = daily_before.json()
        score_before = before_data["daily_progress"]["daily_score"]
        completed_before = list(before_data["daily_progress"]["completed_daily_games"])

        review = self.client.post(
            "/api/topics/review",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(review.status_code, 200)
        review_games = review.json().get("review_games", [])
        review_card = next((card for card in review_games if card.get("game_type") in {"sentence_order", "listening_gap_fill", "mora_romanization"}), None)
        self.assertIsNotNone(review_card)

        payload = self._payload_for_daily_card(review_card)
        evaluated = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": review_card["game_type"],
                "language": review_card["language"],
                "level": review_card["level"],
                "retry_count": 0,
                "review_mode": True,
                "payload": payload,
            },
        )
        self.assertEqual(evaluated.status_code, 200)
        self.assertNotIn("daily_progress", evaluated.json())

        daily_after = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily_after.status_code, 200)
        after_data = daily_after.json()
        self.assertEqual(after_data["daily_progress"]["daily_score"], score_before)
        self.assertEqual(after_data["daily_progress"]["completed_daily_games"], completed_before)

    def test_srs_state_is_created_after_daily_game_evaluation(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]
        card = daily_data["daily_games"][0]

        payload = self._payload_for_daily_card(card)
        evaluated = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": card["game_type"],
                "language": card["language"],
                "level": card["level"],
                "retry_count": 0,
                "payload": payload,
            },
        )
        self.assertEqual(evaluated.status_code, 200)
        self.assertNotIn("error", evaluated.json())

        review_state = api.memory.load_item_review_state(
            learner_id=self.learner_id,
            language="ja",
            topic_key=topic_key,
            game_type=card["game_type"],
            item_id=card["activity_id"],
        )
        self.assertIsNotNone(review_state)
        self.assertEqual(review_state.repetitions, 1)
        self.assertGreaterEqual(review_state.interval_days, 1)
        self.assertGreaterEqual(review_state.ease, 1.3)
        self.assertEqual(review_state.last_score, 100)

    def test_srs_state_resets_repetitions_after_low_score(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]
        sentence_card = next(card for card in daily_data["daily_games"] if card["game_type"] == "sentence_order")

        first_payload = self._payload_for_daily_card(sentence_card)
        first = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": sentence_card["game_type"],
                "language": sentence_card["language"],
                "level": sentence_card["level"],
                "retry_count": 0,
                "payload": first_payload,
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertNotIn("error", first.json())

        wrong_order = list(reversed(first_payload["ordered_tokens_by_user"]))
        second = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": self.learner_id,
                "game_type": sentence_card["game_type"],
                "language": sentence_card["language"],
                "level": sentence_card["level"],
                "retry_count": 0,
                "payload": {
                    "item_id": sentence_card["activity_id"],
                    "ordered_tokens_by_user": wrong_order,
                },
            },
        )
        self.assertEqual(second.status_code, 200)
        self.assertNotIn("error", second.json())

        review_state = api.memory.load_item_review_state(
            learner_id=self.learner_id,
            language="ja",
            topic_key=topic_key,
            game_type=sentence_card["game_type"],
            item_id=sentence_card["activity_id"],
        )
        self.assertIsNotNone(review_state)
        self.assertEqual(review_state.repetitions, 0)
        self.assertGreaterEqual(review_state.lapses, 1)

        due_items = api.memory.list_due_item_review_states(
            learner_id=self.learner_id,
            language="ja",
            current_day_iso=(date.today() + timedelta(days=30)).isoformat(),
            topic_key=topic_key,
        )
        due_ids = {(item.game_type, item.item_id) for item in due_items}
        self.assertIn((sentence_card["game_type"], sentence_card["activity_id"]), due_ids)

    def _close_topic_and_promote_to_level_2(self) -> str:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        daily_data = daily.json()
        topic_key = daily_data["topic"]["topic_key"]

        complete_lesson = self.client.post(
            "/api/games/lesson/complete",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(complete_lesson.status_code, 200)

        for card in daily_data["daily_games"]:
            payload = self._payload_for_daily_card(card)
            evaluation = self.client.post(
                "/api/games/evaluate",
                json={
                    "learner_id": self.learner_id,
                    "game_type": card["game_type"],
                    "language": card["language"],
                    "level": card["level"],
                    "retry_count": 0,
                    "payload": payload,
                },
            )
            self.assertEqual(evaluation.status_code, 200)
            self.assertNotIn("error", evaluation.json())

        weekly_exam = self.client.post(
            "/api/exams/weekly",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(weekly_exam.status_code, 200)
        self.assertTrue(weekly_exam.json().get("passed"))

        level_exam = self.client.post(
            "/api/exams/level",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "target_level": 2,
            },
        )
        self.assertEqual(level_exam.status_code, 200)
        self.assertTrue(level_exam.json().get("passed"))
        self.assertTrue(level_exam.json().get("promoted"))
        return topic_key

    def _payload_for_daily_card(self, card: dict) -> dict:
        payload = {"item_id": card["activity_id"]}
        game_type = card["game_type"]
        card_payload = card.get("payload", {})

        if game_type == "sentence_order":
            payload["ordered_tokens_by_user"] = card_payload.get("ordered_tokens", [])
            return payload

        if game_type == "listening_gap_fill":
            tokens = card_payload.get("tokens", [])
            gap_positions = card_payload.get("gap_positions", [])
            payload["user_gap_tokens"] = [tokens[position] for position in gap_positions]
            return payload

        if game_type == "mora_romanization":
            payload["user_romanized_text"] = MORA_EXPECTED_TEXT_BY_ITEM.get(card["activity_id"], "")
            return payload

        raise AssertionError(f"Unsupported daily game in topic flow test: {game_type}")


if __name__ == "__main__":
    unittest.main()
