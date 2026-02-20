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
        self.assertIn("Listening Gap Fill", display_names)
        self.assertIn("Guided Pronunciation", display_names)
        self.assertIn("Context Quiz", display_names)


if __name__ == "__main__":
    unittest.main()
