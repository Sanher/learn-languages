import unittest

from fastapi.testclient import TestClient

from languages.japanese.app.api import app


class ApiEnglishContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unsupported_language_returns_english_error(self) -> None:
        response = self.client.post(
            "/api/ui/language",
            json={
                "learner_id": "test-user",
                "language": "es",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "Unsupported language: es")

    def test_unsupported_tts_language_returns_english_error(self) -> None:
        response = self.client.post(
            "/api/audio/tts",
            json={
                "language": "en",
                "text": "hello",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "Unsupported language for TTS: en")

    def test_tts_warning_is_returned_after_more_than_three_replays(self) -> None:
        response = self.client.post(
            "/api/audio/tts",
            json={
                "language": "ja",
                "text": "こんにちは",
                "play_count": 4,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json().get("warning"),
            "Warning: repeated TTS playback may increase token usage.",
        )

    def test_tts_warning_is_not_returned_on_third_replay(self) -> None:
        response = self.client.post(
            "/api/audio/tts",
            json={
                "language": "ja",
                "text": "こんにちは",
                "play_count": 3,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("warning", response.json())

    def test_unsupported_game_returns_english_error(self) -> None:
        response = self.client.post(
            "/api/games/evaluate",
            json={
                "game_type": "unknown_game",
                "language": "ja",
                "level": 1,
                "retry_count": 0,
                "payload": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "Unsupported game: unknown_game")

    def test_daily_games_display_names_are_english(self) -> None:
        response = self.client.post("/api/games/daily", json={"learner_id": "test-user"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        display_names = [entry.get("display_name", "") for entry in data.get("all_games", [])]

        self.assertIn("Kanji Match", display_names)
        self.assertIn("Kana Speed Round", display_names)
        self.assertIn("Grammar Particle Fix", display_names)
        self.assertIn("Sentence Order", display_names)
        self.assertIn("Mora Romanization", display_names)
        self.assertIn("Listening Gap Fill", display_names)
        self.assertIn("Guided Pronunciation", display_names)
        self.assertIn("Context Quiz", display_names)

    def test_listening_gap_fill_payload_contains_tts_text(self) -> None:
        response = self.client.post("/api/games/daily", json={"learner_id": "test-user"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        listening_card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "listening_gap_fill"),
            None,
        )
        self.assertIsNotNone(listening_card)
        payload = listening_card.get("payload", {})
        self.assertTrue(payload.get("tts_text"))

    def test_mora_romanization_payload_beginner_contains_mora_guides(self) -> None:
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": "test-user", "level_override_today": 1},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "mora_romanization"),
            None,
        )
        self.assertIsNotNone(card)
        payload = card.get("payload", {})
        self.assertEqual(payload.get("mode"), "beginner")
        self.assertTrue(payload.get("mora_kana_tokens"))
        self.assertTrue(payload.get("mora_romaji_tokens"))
        self.assertEqual(payload.get("japanese_text"), "")

    def test_mora_romanization_payload_advanced_contains_japanese_text_only(self) -> None:
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": "test-user", "level_override_today": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "mora_romanization"),
            None,
        )
        self.assertIsNotNone(card)
        payload = card.get("payload", {})
        self.assertEqual(payload.get("mode"), "advanced")
        self.assertFalse(payload.get("mora_kana_tokens"))
        self.assertFalse(payload.get("mora_romaji_tokens"))
        self.assertTrue(payload.get("japanese_text"))

    def test_mora_romanization_evaluate_advanced_hides_kanji_when_incorrect(self) -> None:
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": "test-user", "level_override_today": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "mora_romanization"),
            None,
        )
        self.assertIsNotNone(card)

        eval_response = self.client.post(
            "/api/games/evaluate",
            json={
                "game_type": "mora_romanization",
                "language": "ja",
                "level": 2,
                "retry_count": 0,
                "payload": {
                    "item_id": card["activity_id"],
                    "user_romanized_text": "kyouwasushiotabemasu",
                },
            },
        )
        self.assertEqual(eval_response.status_code, 200)
        eval_data = eval_response.json()
        self.assertIn("is_correct", eval_data)
        self.assertFalse(eval_data["is_correct"])
        self.assertIsNone(eval_data.get("kanji_mora_line"))

    def test_mora_romanization_evaluate_advanced_shows_kanji_when_correct(self) -> None:
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": "test-user", "level_override_today": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "mora_romanization"),
            None,
        )
        self.assertIsNotNone(card)

        eval_response = self.client.post(
            "/api/games/evaluate",
            json={
                "game_type": "mora_romanization",
                "language": "ja",
                "level": 2,
                "retry_count": 0,
                "payload": {
                    "item_id": card["activity_id"],
                    "user_romanized_text": "kyou wa sushi o tabemasu",
                },
            },
        )
        self.assertEqual(eval_response.status_code, 200)
        eval_data = eval_response.json()
        self.assertTrue(eval_data["is_correct"])
        self.assertTrue(eval_data.get("kanji_mora_line"))


if __name__ == "__main__":
    unittest.main()
