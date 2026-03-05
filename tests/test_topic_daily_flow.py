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
        api._TOPIC_LESSONS_AI_CACHE.clear()
        api._TOPIC_SEQUENCE_CACHE.clear()
        api._TOPIC_SEQUENCE_LOCKS.clear()
        with api.memory._conn() as conn:
            conn.execute("DELETE FROM topic_sequence_cache WHERE language = 'ja'")

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
        self.assertEqual(data["daily_progress"]["extra_games_completed_count"], 0)
        self.assertEqual(data["daily_progress"]["extra_games_completed_types"], [])
        level_progress = data["daily_progress"].get("level_progress")
        self.assertIsInstance(level_progress, dict)
        self.assertEqual(level_progress.get("current_level"), 1)
        self.assertEqual(level_progress.get("next_level"), 2)
        self.assertEqual(level_progress.get("points_current"), 0)
        self.assertEqual(level_progress.get("points_target"), 170)
        self.assertEqual(level_progress.get("points_remaining"), 170)
        self.assertFalse(level_progress.get("level_cap_reached"))
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

    def test_daily_uses_openai_topic_lesson_ladder_when_available(self) -> None:
        ai_lessons = {
            1: {
                "title": "AI beginner title",
                "objective": "AI beginner objective",
                "theory_points": ["AI point 1", "AI point 2"],
                "example_script": "私は学生です。",
                "example_romanized": "watashi wa gakusei desu",
                "example_literal_translation": "I topic student am",
            },
            2: {
                "title": "AI intermediate title",
                "objective": "AI intermediate objective",
                "theory_points": ["AI point 1", "AI point 2"],
                "example_script": "今日は仕事があります。",
                "example_romanized": "kyou wa shigoto ga arimasu",
                "example_literal_translation": "today topic work exists",
            },
            3: {
                "title": "AI advanced title",
                "objective": "AI advanced objective",
                "theory_points": ["AI point 1", "AI point 2"],
                "example_script": "明日友達と映画を見ます。",
                "example_romanized": "ashita tomodachi to eiga o mimasu",
                "example_literal_translation": "tomorrow with friend movie watch",
            },
        }
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_lessons",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "lessons_by_level": ai_lessons,
                    }
                ),
            ) as mock_generate,
        ):
            first = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
            second = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_lesson = first.json()["lesson"]
        self.assertEqual(first_lesson["title"], "AI beginner title")
        self.assertEqual(first_lesson["objective"], "AI beginner objective")
        self.assertEqual(mock_generate.await_count, 1)

    def test_topic_lessons_refresh_flag_regenerates_after_cache_cold_start(self) -> None:
        first_lessons = {
            1: {
                "title": "AI ladder v1",
                "objective": "Objective v1",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "私は学生です。",
                "example_romanized": "watashi wa gakusei desu",
                "example_literal_translation": "I topic student am",
            },
            2: {
                "title": "AI ladder v1 mid",
                "objective": "Objective v1 mid",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "今日は仕事があります。",
                "example_romanized": "kyou wa shigoto ga arimasu",
                "example_literal_translation": "today topic work exists",
            },
            3: {
                "title": "AI ladder v1 adv",
                "objective": "Objective v1 adv",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "明日友達と映画を見ます。",
                "example_romanized": "ashita tomodachi to eiga o mimasu",
                "example_literal_translation": "tomorrow with friend movie watch",
            },
        }
        second_lessons = {
            1: {
                "title": "AI ladder v2",
                "objective": "Objective v2",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "私は学生です。",
                "example_romanized": "watashi wa gakusei desu",
                "example_literal_translation": "I topic student am",
            },
            2: {
                "title": "AI ladder v2 mid",
                "objective": "Objective v2 mid",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "今日は仕事があります。",
                "example_romanized": "kyou wa shigoto ga arimasu",
                "example_literal_translation": "today topic work exists",
            },
            3: {
                "title": "AI ladder v2 adv",
                "objective": "Objective v2 adv",
                "theory_points": ["Point 1", "Point 2"],
                "example_script": "明日友達と映画を見ます。",
                "example_romanized": "ashita tomodachi to eiga o mimasu",
                "example_literal_translation": "tomorrow with friend movie watch",
            },
        }
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_lessons",
                new=unittest.mock.AsyncMock(
                    side_effect=[
                        {"source": "openai", "lessons_by_level": first_lessons},
                        {"source": "openai", "lessons_by_level": second_lessons},
                    ]
                ),
            ) as mock_generate,
        ):
            api.memory.set_topic_lessons_refresh_required(
                language="ja",
                topic_key="identity_and_plans",
                required=True,
            )
            first = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["lesson"]["title"], "AI ladder v1")
            topic_key = first.json()["topic"]["topic_key"]

            api.memory.set_topic_lessons_refresh_required(language="ja", topic_key=topic_key, required=True)
            api._TOPIC_LESSONS_AI_CACHE.clear()  # simulate restart: runtime cache disappears

            second = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["lesson"]["title"], "AI ladder v2")
            self.assertEqual(mock_generate.await_count, 2)

    def test_daily_bootstraps_topic_sequence_from_openai_once(self) -> None:
        ai_topics = [
            {
                "topic_key": "basic_greetings",
                "title": "Basic greetings",
                "description": "Use simple greetings and introductions.",
                "stage": "basic",
            },
            {
                "topic_key": "daily_routines",
                "title": "Daily routines",
                "description": "Describe regular activities and schedules.",
                "stage": "intermediate",
            },
            {
                "topic_key": "future_hypotheticals",
                "title": "Future hypotheticals",
                "description": "Discuss plans and hypothetical outcomes.",
                "stage": "advanced",
            },
        ]
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "topics": ai_topics,
                    }
                ),
            ) as mock_generate_sequence,
        ):
            first = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
            second = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["topic"]["topic_key"], "basic_greetings")
        self.assertEqual(second.json()["topic"]["topic_key"], "basic_greetings")
        self.assertEqual(mock_generate_sequence.await_count, 1)
        persisted_topics, persisted_source = api.memory.load_topic_sequence_cache(language="ja")
        self.assertIsNotNone(persisted_topics)
        self.assertEqual(len(persisted_topics or []), 3)
        self.assertEqual(persisted_source, "openai")

    def test_daily_topic_uses_next_sequence_topic_after_closure(self) -> None:
        ai_topics = [
            {
                "topic_key": "basic_greetings",
                "title": "Basic greetings",
                "description": "Use simple greetings and introductions.",
                "stage": "basic",
            },
            {
                "topic_key": "daily_routines",
                "title": "Daily routines",
                "description": "Describe regular activities and schedules.",
                "stage": "intermediate",
            },
        ]
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "topics": ai_topics,
                    }
                ),
            ),
        ):
            first = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["topic"]["topic_key"], "basic_greetings")

        api.memory.mark_topic_closed(
            learner_id=self.learner_id,
            language="ja",
            topic_key="basic_greetings",
            closed_day_iso=date.today().isoformat(),
            closed_level=2,
            reason="test_closure",
        )
        next_daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(next_daily.status_code, 200)
        self.assertEqual(next_daily.json()["topic"]["topic_key"], "daily_routines")

    def test_topic_refresh_endpoint_applies_openai_sequence(self) -> None:
        ai_topics = [
            {
                "topic_key": "basic_greetings",
                "title": "Basic greetings",
                "description": "Use simple greetings and introductions.",
                "stage": "basic",
            },
            {
                "topic_key": "daily_routines",
                "title": "Daily routines",
                "description": "Describe regular activities and schedules.",
                "stage": "intermediate",
            },
        ]
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "topics": ai_topics,
                    }
                ),
            ) as mock_generate_sequence,
        ):
            refresh = self.client.post(
                "/api/topics/refresh",
                json={"learner_id": self.learner_id, "language": "ja"},
            )
            self.assertEqual(refresh.status_code, 200)
            refresh_data = refresh.json()
            self.assertTrue(refresh_data.get("refreshed"))
            self.assertEqual(refresh_data.get("source"), "openai")
            self.assertEqual(refresh_data.get("topic_count"), 2)
            self.assertEqual(refresh_data.get("active_topic", {}).get("topic_key"), "basic_greetings")
            self.assertEqual(mock_generate_sequence.await_count, 1)

        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        self.assertEqual(daily.json()["topic"]["topic_key"], "basic_greetings")

    def test_topic_refresh_endpoint_keeps_existing_sequence_on_fallback(self) -> None:
        ai_topics = [
            {
                "topic_key": "basic_greetings",
                "title": "Basic greetings",
                "description": "Use simple greetings and introductions.",
                "stage": "basic",
            },
            {
                "topic_key": "daily_routines",
                "title": "Daily routines",
                "description": "Describe regular activities and schedules.",
                "stage": "intermediate",
            },
        ]
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "topics": ai_topics,
                    }
                ),
            ),
        ):
            first_refresh = self.client.post(
                "/api/topics/refresh",
                json={"learner_id": self.learner_id, "language": "ja"},
            )
            self.assertEqual(first_refresh.status_code, 200)
            self.assertTrue(first_refresh.json().get("refreshed"))

        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "fallback",
                        "topics": [
                            {
                                "topic_key": "identity_and_plans",
                                "title": "Identity and Daily Plans",
                                "description": "Fallback topic.",
                                "stage": "basic",
                            }
                        ],
                        "error": "Topic sequence request failed: timeout",
                    }
                ),
            ),
        ):
            refresh = self.client.post(
                "/api/topics/refresh",
                json={"learner_id": self.learner_id, "language": "ja"},
            )
            self.assertEqual(refresh.status_code, 200)
            refresh_data = refresh.json()
            self.assertFalse(refresh_data.get("refreshed"))
            self.assertEqual(refresh_data.get("source"), "fallback")
            self.assertIn("timeout", refresh_data.get("error", ""))

        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        self.assertEqual(daily.json()["topic"]["topic_key"], "basic_greetings")

    def test_topic_refresh_endpoint_selects_next_active_topic_when_first_is_closed(self) -> None:
        ai_topics = [
            {
                "topic_key": "basic_greetings",
                "title": "Basic greetings",
                "description": "Use simple greetings and introductions.",
                "stage": "basic",
            },
            {
                "topic_key": "daily_routines",
                "title": "Daily routines",
                "description": "Describe regular activities and schedules.",
                "stage": "intermediate",
            },
        ]
        api.memory.mark_topic_closed(
            learner_id=self.learner_id,
            language="ja",
            topic_key="basic_greetings",
            closed_day_iso=date.today().isoformat(),
            closed_level=2,
            reason="test_closed_before_refresh",
        )
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "openai",
                        "topics": ai_topics,
                    }
                ),
            ),
        ):
            refresh = self.client.post(
                "/api/topics/refresh",
                json={"learner_id": self.learner_id, "language": "ja"},
            )
        self.assertEqual(refresh.status_code, 200)
        refresh_data = refresh.json()
        self.assertTrue(refresh_data.get("refreshed"))
        self.assertEqual(refresh_data.get("topic_count"), 2)
        self.assertEqual(refresh_data.get("active_topic", {}).get("topic_key"), "daily_routines")

    def test_topic_refresh_endpoint_without_existing_sequence_returns_non_empty_fallback(self) -> None:
        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_topic_sequence",
                new=unittest.mock.AsyncMock(
                    return_value={
                        "source": "fallback",
                        "topics": "invalid",
                        "error": "Topic sequence request failed: timeout",
                    }
                ),
            ) as mock_generate_sequence,
        ):
            refresh = self.client.post(
                "/api/topics/refresh",
                json={"learner_id": self.learner_id, "language": "ja"},
            )

        self.assertEqual(refresh.status_code, 200)
        refresh_data = refresh.json()
        self.assertFalse(refresh_data.get("refreshed"))
        self.assertEqual(refresh_data.get("source"), "fallback")
        self.assertGreater(refresh_data.get("topic_count", 0), 0)
        self.assertTrue(refresh_data.get("active_topic", {}).get("topic_key"))
        self.assertEqual(mock_generate_sequence.await_count, 1)

    def test_lesson_complete_triggers_translation_prewarm_task(self) -> None:
        daily = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})
        self.assertEqual(daily.status_code, 200)
        lesson = daily.json()["lesson"]

        with unittest.mock.patch.object(api, "_prewarm_lesson_daily_translation_cache") as mock_prewarm:
            complete_lesson = self.client.post(
                "/api/games/lesson/complete",
                json={
                    "learner_id": self.learner_id,
                    "language": "ja",
                    "topic_key": lesson["topic_key"],
                },
            )

        self.assertEqual(complete_lesson.status_code, 200)
        self.assertEqual(mock_prewarm.call_count, 1)
        kwargs = mock_prewarm.call_args.kwargs
        self.assertEqual(kwargs["learner_id"], self.learner_id)
        self.assertEqual(kwargs["language"], "ja")
        self.assertEqual(kwargs["level"], 1)
        self.assertEqual(kwargs["topic"].topic_key, lesson["topic_key"])

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

    def test_auto_level_promotion_returns_level_up_notice(self) -> None:
        with unittest.mock.patch.object(api.planner, "difficulty_for", return_value=5):
            response = self.client.post("/api/games/daily", json={"learner_id": self.learner_id})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        notice = data.get("level_up_notice")
        self.assertIsNotNone(notice)
        self.assertEqual(notice["from_level"], 1)
        self.assertEqual(notice["to_level"], 2)
        self.assertIn("Level up!", notice["message"])
        self.assertEqual(data["current_level"], 2)
        self.assertEqual(data["today_level"], 2)

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
        self.assertGreaterEqual(after_data["daily_progress"]["extra_games_completed_count"], 1)
        self.assertIn("grammar_particle_fix", after_data["daily_progress"]["extra_games_completed_types"])

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
        self._seed_topic_mastery_level_three(topic_key)

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
        self._seed_topic_mastery_level_three(topic_key)

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

    def test_weekly_exam_locked_when_topic_mastery_below_minimum(self) -> None:
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

        weekly_exam = self.client.post(
            "/api/exams/weekly",
            json={
                "learner_id": self.learner_id,
                "language": "ja",
                "topic_key": topic_key,
            },
        )
        self.assertEqual(weekly_exam.status_code, 200)
        data = weekly_exam.json()
        self.assertIn("error", data)
        self.assertTrue("mastery level" in str(data["error"]).lower())
        self.assertIn("daily_progress", data)
        self.assertFalse(data["daily_progress"]["topic_mastery_ready_for_weekly_exam"])
        self.assertLess(data["daily_progress"]["topic_mastery_level"], 3)

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
        self._seed_topic_mastery_level_three(topic_key)

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

    def test_topic_review_attaches_ai_generated_prompt_when_openai_available(self) -> None:
        topic_key = self._close_topic_and_promote_to_level_2()

        async def _fake_daily_content(*, difficulty: int, games: list[str], learner_note: str) -> dict:
            return {
                "source": "openai",
                "activities": [
                    {"game": game, "prompt": f"Review AI prompt for {game} at {difficulty}."}
                    for game in games
                ],
            }

        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_daily_content",
                new=unittest.mock.AsyncMock(side_effect=_fake_daily_content),
            ) as mock_generate,
        ):
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
        self.assertGreater(mock_generate.await_count, 0)
        self.assertGreaterEqual(len(data.get("review_games", [])), 3)
        self.assertTrue(all(bool(card.get("ai_generated_prompt")) for card in data["review_games"]))
        self.assertTrue(all(card.get("ai_prompt_source") == "openai" for card in data["review_games"]))

    def test_topic_review_does_not_attach_ai_prompt_when_generation_falls_back(self) -> None:
        topic_key = self._close_topic_and_promote_to_level_2()

        async def _fake_fallback(*, difficulty: int, games: list[str], learner_note: str) -> dict:
            return {
                "source": "fallback",
                "activities": [
                    {"game": game, "prompt": f"Fallback prompt {game}"}
                    for game in games
                ],
            }

        with (
            unittest.mock.patch.object(api.openai_planner, "api_key", "test-openai-key"),
            unittest.mock.patch.object(
                api.openai_planner,
                "generate_daily_content",
                new=unittest.mock.AsyncMock(side_effect=_fake_fallback),
            ),
        ):
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
        self.assertGreaterEqual(len(data.get("review_games", [])), 3)
        self.assertTrue(all(not card.get("ai_generated_prompt") for card in data["review_games"]))

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
        self._seed_topic_mastery_level_three(topic_key)

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

    def _seed_topic_mastery_level_three(self, topic_key: str, language: str = "ja") -> None:
        topic_definition = api._topic_definition_for_key(language, topic_key)
        self.assertIsNotNone(topic_definition)
        daily_games = [game for game, _activity_id in topic_definition.daily_plan_for_level(1)]
        self.assertGreaterEqual(len(daily_games), 1)

        existing_days = api.memory.count_days_on_topic(
            learner_id=self.learner_id,
            language=language,
            topic_key=topic_key,
        )
        required_days = 5
        missing_days = max(0, required_days - existing_days)
        if missing_days <= 0:
            return

        per_game_score = max(1, 150 // len(daily_games))
        for idx in range(missing_days):
            day_iso = (date.today() - timedelta(days=idx + 1)).isoformat()
            api.memory.mark_lesson_completed(
                learner_id=self.learner_id,
                day_iso=day_iso,
                language=language,
                topic_key=topic_key,
            )
            for game_type in daily_games:
                api.memory.mark_daily_game_completed(
                    learner_id=self.learner_id,
                    day_iso=day_iso,
                    language=language,
                    topic_key=topic_key,
                    game_type=game_type,
                )
                api.memory.upsert_daily_game_score(
                    learner_id=self.learner_id,
                    day_iso=day_iso,
                    language=language,
                    topic_key=topic_key,
                    game_type=game_type,
                    score=per_game_score,
                    allowed_daily_games=daily_games,
                )

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
