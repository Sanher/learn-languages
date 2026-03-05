import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from languages.japanese.app import api
from languages.japanese.app.api import app


class ApiEnglishContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertIn("providers", payload)
        self.assertIn("openai_configured", payload["providers"])
        self.assertIn("elevenlabs_configured", payload["providers"])
        self.assertIn("storage", payload)
        self.assertIn("db_exists", payload["storage"])
        self.assertIn("db_writable_parent", payload["storage"])

    def test_missing_web_asset_returns_404(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/web/missing.js")
        self.assertEqual(response.status_code, 404)

    def test_web_path_traversal_returns_404(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/web/%2e%2e/%2e%2e/README.md")
        self.assertEqual(response.status_code, 404)

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

    def test_topic_refresh_rejects_unsupported_language(self) -> None:
        response = self.client.post(
            "/api/topics/refresh",
            json={
                "learner_id": "test-user",
                "language": "es",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "Unsupported language: es")

    def test_secondary_translation_rejects_unsupported_language(self) -> None:
        response = self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": "test-user",
                "secondary_language": "fr",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], "Unsupported secondary translation language: fr")

    def test_secondary_translation_contract_is_present_in_daily_payload(self) -> None:
        response = self.client.post("/api/games/daily", json={"learner_id": "test-user-translation-contract"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        preferences = data.get("translation_preferences", {})
        self.assertEqual(preferences.get("primary_translation_language"), "en")
        self.assertIsNone(preferences.get("secondary_translation_language"))
        self.assertIn("secondary_translation_provider_available", preferences)
        self.assertEqual(
            preferences.get("secondary_translation_provider_available"),
            bool(api.openai_planner.api_key),
        )
        self.assertIn(
            {"code": "es", "label": "Español"},
            preferences.get("available_secondary_translation_languages", []),
        )

    def test_secondary_translation_persists_in_daily_payload(self) -> None:
        learner_id = "test-user-translation-es"
        save = self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "es",
            },
        )
        self.assertEqual(save.status_code, 200)
        self.assertEqual(save.json()["translation_preferences"]["secondary_translation_language"], "es")
        self.assertEqual(
            save.json()["translation_preferences"]["secondary_translation_provider_available"],
            bool(api.openai_planner.api_key),
        )

        daily = self.client.post("/api/games/daily", json={"learner_id": learner_id})
        self.assertEqual(daily.status_code, 200)
        self.assertEqual(daily.json()["translation_preferences"]["secondary_translation_language"], "es")

    def test_secondary_translation_can_be_disabled_with_off(self) -> None:
        learner_id = "test-user-translation-off"
        self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "es",
            },
        )
        disable = self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "off",
            },
        )
        self.assertEqual(disable.status_code, 200)
        self.assertIsNone(disable.json()["translation_preferences"]["secondary_translation_language"])

        daily = self.client.post("/api/games/daily", json={"learner_id": learner_id})
        self.assertEqual(daily.status_code, 200)
        self.assertIsNone(daily.json()["translation_preferences"]["secondary_translation_language"])

    def test_secondary_translation_update_keeps_learning_language(self) -> None:
        learner_id = "test-user-translation-language-stable"
        self.client.post(
            "/api/ui/language",
            json={
                "learner_id": learner_id,
                "language": "ja",
            },
        )
        updated = self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "es",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json().get("language"), "ja")

    def test_daily_payload_includes_translation_bundles_for_lesson_and_prompts(self) -> None:
        learner_id = "test-user-translation-bundles"
        self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "es",
            },
        )
        daily = self.client.post("/api/games/daily", json={"learner_id": learner_id})
        self.assertEqual(daily.status_code, 200)
        data = daily.json()

        lesson = data["lesson"]
        self.assertIn("objective_translations", lesson)
        self.assertEqual(lesson["objective_translations"]["en"], lesson["objective"])
        self.assertEqual(lesson["objective_translations"]["secondary_lang"], "es")
        self.assertIn("title_translations", lesson)
        self.assertEqual(lesson["title_translations"]["en"], lesson["title"])
        self.assertEqual(lesson["title_translations"]["secondary_lang"], "es")
        topic = data["topic"]
        self.assertIn("title_translations", topic)
        self.assertEqual(topic["title_translations"]["en"], topic["title"])
        self.assertEqual(topic["title_translations"]["secondary_lang"], "es")
        self.assertIn("description_translations", topic)
        self.assertEqual(topic["description_translations"]["en"], topic["description"])
        self.assertEqual(topic["description_translations"]["secondary_lang"], "es")

        first_card = data["daily_games"][0]
        self.assertIn("prompt_translations", first_card)
        self.assertEqual(first_card["prompt_translations"]["en"], first_card["prompt"])
        self.assertEqual(first_card["prompt_translations"]["secondary_lang"], "es")

    def test_daily_payload_attaches_ai_generated_prompt_when_openai_available(self) -> None:
        learner_id = f"test-user-ai-prompts-{uuid4().hex}"

        async def _fake_daily_content(*, difficulty: int, games: list[str], learner_note: str) -> dict:
            return {
                "source": "openai",
                "activities": [
                    {"game": game, "prompt": f"AI prompt for {game} at difficulty {difficulty}."}
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
            daily = self.client.post("/api/games/daily", json={"learner_id": learner_id})

        self.assertEqual(daily.status_code, 200)
        cards = daily.json().get("daily_games", [])
        self.assertEqual(mock_generate.await_count, 1)
        self.assertGreater(len(cards), 0)
        self.assertTrue(all(bool(card.get("ai_generated_prompt")) for card in cards))
        self.assertTrue(all(card.get("ai_prompt_source") == "openai" for card in cards))

    def test_game_evaluation_includes_translation_bundle_feedback(self) -> None:
        learner_id = "test-user-translation-eval"
        self.client.post(
            "/api/ui/secondary-translation",
            json={
                "learner_id": learner_id,
                "secondary_language": "es",
            },
        )
        daily = self.client.post("/api/games/daily", json={"learner_id": learner_id})
        self.assertEqual(daily.status_code, 200)
        card = next((entry for entry in daily.json().get("daily_games", []) if entry.get("game_type") == "sentence_order"), None)
        self.assertIsNotNone(card)
        payload = {
            "item_id": card["activity_id"],
            "ordered_tokens_by_user": card.get("payload", {}).get("ordered_tokens", []),
        }
        evaluation = self.client.post(
            "/api/games/evaluate",
            json={
                "learner_id": learner_id,
                "game_type": "sentence_order",
                "language": "ja",
                "level": card["level"],
                "retry_count": 0,
                "payload": payload,
            },
        )
        self.assertEqual(evaluation.status_code, 200)
        evaluated = evaluation.json()
        self.assertIn("feedback", evaluated)
        self.assertIn("feedback_translations", evaluated)
        self.assertEqual(evaluated["feedback_translations"]["en"], evaluated["feedback"])
        self.assertEqual(evaluated["feedback_translations"]["secondary_lang"], "es")

    def test_translation_cache_roundtrip(self) -> None:
        cache_key = f"test-cache-key-{uuid4().hex}"
        self.assertIsNone(api.memory.load_cached_translation(cache_key))
        api.memory.save_cached_translation(
            cache_key=cache_key,
            source_text="good morning",
            source_language="en",
            target_language="es",
            context="unit-test",
            translated_text="buenos días",
            updated_at_iso="2026-03-01T00:00:00",
        )
        self.assertEqual(api.memory.load_cached_translation(cache_key), "buenos días")

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

    def test_mora_romanization_payload_intermediate_keeps_mora_romaji(self) -> None:
        learner_id = "test-user-level2"
        api.memory.set_language_level(learner_id, "ja", 2)
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": learner_id, "level_override_today": 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        card = next(
            (entry for entry in data.get("all_games", []) if entry.get("game_type") == "mora_romanization"),
            None,
        )
        self.assertIsNotNone(card)
        payload = card.get("payload", {})
        self.assertEqual(payload.get("mode"), "intermediate")
        self.assertTrue(payload.get("mora_kana_tokens"))
        self.assertTrue(payload.get("mora_romaji_tokens"))
        self.assertEqual(payload.get("japanese_text"), "")

    def test_mora_romanization_payload_advanced_contains_japanese_text_only(self) -> None:
        learner_id = "test-user-level3"
        api.memory.set_language_level(learner_id, "ja", 3)
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": learner_id, "level_override_today": 3},
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
        learner_id = "test-user-level3-hide"
        api.memory.set_language_level(learner_id, "ja", 3)
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": learner_id, "level_override_today": 3},
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
                "level": 3,
                "retry_count": 0,
                "payload": {
                    "item_id": card["activity_id"],
                    "user_romanized_text": "ashitatomodachitoeigaomimasu",
                },
            },
        )
        self.assertEqual(eval_response.status_code, 200)
        eval_data = eval_response.json()
        self.assertIn("is_correct", eval_data)
        self.assertFalse(eval_data["is_correct"])
        self.assertIsNone(eval_data.get("kanji_mora_line"))
        self.assertTrue(eval_data.get("sequence_mismatches"))

    def test_mora_romanization_evaluate_advanced_shows_kanji_when_correct(self) -> None:
        learner_id = "test-user-level3-show"
        api.memory.set_language_level(learner_id, "ja", 3)
        response = self.client.post(
            "/api/games/daily",
            json={"learner_id": learner_id, "level_override_today": 3},
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
                "level": 3,
                "retry_count": 0,
                "payload": {
                    "item_id": card["activity_id"],
                    "user_romanized_text": "ashita tomodachi to eiga o mimasu",
                },
            },
        )
        self.assertEqual(eval_response.status_code, 200)
        eval_data = eval_response.json()
        self.assertTrue(eval_data["is_correct"])
        self.assertTrue(eval_data.get("kanji_mora_line"))


if __name__ == "__main__":
    unittest.main()
