import unittest
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
        self.assertFalse(data["daily_progress"]["lesson_completed"])
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

    def test_topic_stays_the_same_when_level_is_lowered(self) -> None:
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
        self.assertEqual(lowered_data["today_level"], 2)
        self.assertEqual(high_data["topic"]["topic_key"], lowered_data["topic"]["topic_key"])
        self.assertNotEqual(high_data["lesson"]["title"], lowered_data["lesson"]["title"])

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
