import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from languages.japanese.app.services.elevenlabs_client import ElevenLabsService
from languages.japanese.app.services.openai_client import OpenAIPlanner
from languages.japanese.app.services.runtime_config import clear_cached_options, get_setting


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_cached_options()

    def tearDown(self) -> None:
        clear_cached_options()

    def test_get_setting_prefers_env_over_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            options_path = os.path.join(tmp_dir, "options.json")
            with open(options_path, "w", encoding="utf-8") as file:
                json.dump({"openai_api_key": "from-options"}, file)

            with patch.dict(
                os.environ,
                {
                    "HA_ADDON_OPTIONS_PATH": options_path,
                    "OPENAI_API_KEY": "from-env",
                },
                clear=False,
            ):
                value = get_setting(
                    env_names=("OPENAI_API_KEY",),
                    option_names=("openai_api_key",),
                    default="",
                )
                self.assertEqual(value, "from-env")

    def test_get_setting_reads_from_options_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            options_path = os.path.join(tmp_dir, "options.json")
            with open(options_path, "w", encoding="utf-8") as file:
                json.dump({"openai_api_key": "from-options"}, file)

            with patch.dict(os.environ, {"HA_ADDON_OPTIONS_PATH": options_path}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                clear_cached_options()
                value = get_setting(
                    env_names=("OPENAI_API_KEY",),
                    option_names=("openai_api_key",),
                    default="",
                )
                self.assertEqual(value, "from-options")

    def test_openai_planner_uses_options_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            options_path = os.path.join(tmp_dir, "options.json")
            with open(options_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "openai": {
                            "api_key": "openai-from-options",
                            "model": "gpt-4.1-mini",
                            "stt_models": "whisper-1,gpt-4o-mini-transcribe",
                        }
                    },
                    file,
                )

            with patch.dict(os.environ, {"HA_ADDON_OPTIONS_PATH": options_path}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("OPENAI_MODEL", None)
                os.environ.pop("OPENAI_STT_MODELS", None)
                clear_cached_options()
                planner = OpenAIPlanner()
                self.assertEqual(planner.api_key, "openai-from-options")
                self.assertEqual(planner.model, "gpt-4.1-mini")
                self.assertEqual(planner.stt_models, ["whisper-1", "gpt-4o-mini-transcribe"])

    def test_elevenlabs_service_uses_options_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            options_path = os.path.join(tmp_dir, "options.json")
            with open(options_path, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "elevenlabs_api_key": "eleven-key",
                        "elevenlabs_voice_id": "voice-123",
                        "elevenlabs_model_id": "eleven_turbo_v2_5",
                    },
                    file,
                )

            with patch.dict(os.environ, {"HA_ADDON_OPTIONS_PATH": options_path}, clear=False):
                os.environ.pop("ELEVENLABS_API_KEY", None)
                os.environ.pop("ELEVENLABS_VOICE_ID", None)
                os.environ.pop("ELEVENLABS_MODEL_ID", None)
                clear_cached_options()
                service = ElevenLabsService()
                self.assertEqual(service.api_key, "eleven-key")
                self.assertEqual(service.voice_id, "voice-123")
                self.assertEqual(service.model_id, "eleven_turbo_v2_5")

    def test_translation_circuit_breaker_opens_after_consecutive_failures(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_TRANSLATION_FAILURE_THRESHOLD": "2",
                "OPENAI_TRANSLATION_COOLDOWN_SECONDS": "300",
            },
            clear=False,
        ):
            clear_cached_options()
            planner = OpenAIPlanner()
            with patch("languages.japanese.app.services.openai_client.httpx.Client") as mock_client:
                mock_http = mock_client.return_value.__enter__.return_value
                mock_http.post.side_effect = httpx.ConnectError("network down")

                first = planner.translate_text(source_text="hello", target_language="es")
                second = planner.translate_text(source_text="world", target_language="es")
                third = planner.translate_text(source_text="again", target_language="es")

                self.assertIn("Translation request failed", first.get("error", ""))
                self.assertIn("Translation request failed", second.get("error", ""))
                self.assertEqual(
                    third.get("error"),
                    "Translation temporarily unavailable due to repeated provider failures.",
                )
                self.assertEqual(mock_http.post.call_count, 2)

    def test_translate_text_rejects_overlong_source_text_before_network_call(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_TRANSLATION_MAX_TEXT_CHARS": "40",
            },
            clear=False,
        ):
            clear_cached_options()
            planner = OpenAIPlanner()
            self.assertEqual(planner.translation_max_text_chars, 60)
            with patch("languages.japanese.app.services.openai_client.httpx.Client") as mock_client:
                response = planner.translate_text(
                    source_text="x" * 61,
                    target_language="es",
                    context="unit-test",
                )
                self.assertEqual(response.get("source"), "fallback")
                self.assertEqual(response.get("error"), "Source text is too long for translation.")
                self.assertEqual(mock_client.call_count, 0)

    def test_generate_daily_content_parses_json_activities_and_fills_missing_games(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            with patch("languages.japanese.app.services.openai_client.httpx.AsyncClient") as mock_client:
                mock_http = mock_client.return_value.__aenter__.return_value
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_response.json.return_value = {
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "{\"activities\":[{\"game\":\"sentence_order\",\"prompt\":\"Arrange this sentence politely.\"}]}",
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_daily_content(
                        difficulty=4,
                        games=["sentence_order", "listening_gap_fill"],
                        learner_note="topic test",
                    )
                )

                self.assertEqual(result.get("source"), "openai")
                activities = result.get("activities", [])
                self.assertEqual(len(activities), 2)
                self.assertEqual(activities[0]["game"], "sentence_order")
                self.assertEqual(activities[0]["prompt"], "Arrange this sentence politely.")
                self.assertEqual(activities[1]["game"], "listening_gap_fill")
                self.assertIn("Level 4", activities[1]["prompt"])

    def test_generate_daily_content_falls_back_when_provider_fails(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            with patch("languages.japanese.app.services.openai_client.httpx.AsyncClient") as mock_client:
                mock_http = mock_client.return_value.__aenter__.return_value
                mock_http.post = AsyncMock(side_effect=httpx.ConnectError("network down"))

                result = asyncio.run(
                    planner.generate_daily_content(
                        difficulty=5,
                        games=["mora_romanization"],
                        learner_note="topic test",
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertIn("Daily content request failed", result.get("error", ""))
                activities = result.get("activities", [])
                self.assertEqual(len(activities), 1)
                self.assertEqual(activities[0]["game"], "mora_romanization")
                self.assertIn("Level 5", activities[0]["prompt"])

    def test_generate_daily_content_falls_back_when_output_is_invalid_json(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            with patch("languages.japanese.app.services.openai_client.httpx.AsyncClient") as mock_client:
                mock_http = mock_client.return_value.__aenter__.return_value
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_response.json.return_value = {
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "not-json",
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_daily_content(
                        difficulty=6,
                        games=["sentence_order", "context_quiz"],
                        learner_note="invalid-json-test",
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertEqual(result.get("error"), "Invalid JSON daily content output.")
                activities = result.get("activities", [])
                self.assertEqual(len(activities), 2)
                self.assertEqual(activities[0]["game"], "sentence_order")
                self.assertEqual(activities[1]["game"], "context_quiz")


if __name__ == "__main__":
    unittest.main()
