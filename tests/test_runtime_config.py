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

    def test_generate_topic_lessons_returns_progressive_levels(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            fallback_lessons = {
                1: {
                    "title": "Fallback 1",
                    "objective": "Fallback objective 1",
                    "theory_points": ["Point 1", "Point 2"],
                    "example_script": "私は学生です。",
                    "example_romanized": "watashi wa gakusei desu",
                    "example_literal_translation": "I topic student am",
                },
                2: {
                    "title": "Fallback 2",
                    "objective": "Fallback objective 2",
                    "theory_points": ["Point 1", "Point 2"],
                    "example_script": "今日は仕事があります。",
                    "example_romanized": "kyou wa shigoto ga arimasu",
                    "example_literal_translation": "today topic work exists",
                },
                3: {
                    "title": "Fallback 3",
                    "objective": "Fallback objective 3",
                    "theory_points": ["Point 1", "Point 2"],
                    "example_script": "明日友達と映画を見ます。",
                    "example_romanized": "ashita tomodachi to eiga o mimasu",
                    "example_literal_translation": "tomorrow with friend movie watch",
                },
            }
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
                                    "text": json.dumps(
                                        {
                                            "lessons_by_level": {
                                                "1": {
                                                    "title": "Beginner identity patterns",
                                                    "objective": "Build basic self-introduction sentences.",
                                                    "theory_points": [
                                                        "Use wa to mark topic.",
                                                        "Keep noun + desu ending.",
                                                    ],
                                                    "example_script": "私は学生です。",
                                                    "example_romanized": "watashi wa gakusei desu",
                                                    "example_literal_translation": "I topic student am",
                                                },
                                                "2": {
                                                    "title": "Daily routine statements",
                                                    "objective": "Describe daily schedule context naturally.",
                                                    "theory_points": [
                                                        "Add time words early.",
                                                        "Use ga for existence/subject focus.",
                                                    ],
                                                    "example_script": "今日は仕事があります。",
                                                    "example_romanized": "kyou wa shigoto ga arimasu",
                                                    "example_literal_translation": "today topic work exists",
                                                },
                                                "3": {
                                                    "title": "Advanced plan chaining",
                                                    "objective": "Connect time, companion and action in one sentence.",
                                                    "theory_points": [
                                                        "Anchor with time at start.",
                                                        "Keep verb at the end.",
                                                    ],
                                                    "example_script": "明日友達と映画を見ます。",
                                                    "example_romanized": "ashita tomodachi to eiga o mimasu",
                                                    "example_literal_translation": "tomorrow with friend movie watch",
                                                },
                                            }
                                        }
                                    ),
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_topic_lessons(
                        language="ja",
                        topic_key="identity_and_plans",
                        topic_title="Identity and Daily Plans",
                        topic_description="topic test",
                        fallback_lessons_by_level=fallback_lessons,
                    )
                )

                self.assertEqual(result.get("source"), "openai")
                lessons = result.get("lessons_by_level", {})
                self.assertEqual(lessons[1]["title"], "Beginner identity patterns")
                self.assertEqual(lessons[2]["title"], "Daily routine statements")
                self.assertEqual(lessons[3]["title"], "Advanced plan chaining")

    def test_generate_topic_lessons_falls_back_when_levels_are_incomplete(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            fallback_lessons = {
                1: {"title": "Fallback 1", "objective": "o1", "theory_points": ["a", "b"], "example_script": "a", "example_romanized": "a", "example_literal_translation": "a"},
                2: {"title": "Fallback 2", "objective": "o2", "theory_points": ["a", "b"], "example_script": "b", "example_romanized": "b", "example_literal_translation": "b"},
                3: {"title": "Fallback 3", "objective": "o3", "theory_points": ["a", "b"], "example_script": "c", "example_romanized": "c", "example_literal_translation": "c"},
            }
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
                                    "text": '{"lessons_by_level":{"1":{"title":"ok","objective":"ok","theory_points":["a","b"],"example_script":"a","example_romanized":"a","example_literal_translation":"a"}}}',
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_topic_lessons(
                        language="ja",
                        topic_key="identity_and_plans",
                        topic_title="Identity and Daily Plans",
                        topic_description="topic test",
                        fallback_lessons_by_level=fallback_lessons,
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertIn("Missing lesson levels", result.get("error", ""))
                self.assertEqual(result.get("lessons_by_level", {}), fallback_lessons)

    def test_generate_topic_sequence_returns_topics_ordered_by_stage(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            fallback_topics = [
                {
                    "topic_key": "identity_and_plans",
                    "title": "Identity and Daily Plans",
                    "description": "Fallback identity topic.",
                    "stage": "basic",
                }
            ]
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
                                    "text": json.dumps(
                                        {
                                            "topics": [
                                                {
                                                    "topic_key": "future_hypotheticals",
                                                    "title": "Future hypotheticals",
                                                    "description": "Discuss hypothetical futures.",
                                                    "stage": "advanced",
                                                },
                                                {
                                                    "topic_key": "basic_greetings",
                                                    "title": "Basic greetings",
                                                    "description": "Use simple daily greetings.",
                                                    "stage": "basic",
                                                },
                                                {
                                                    "topic_key": "routine_narration",
                                                    "title": "Routine narration",
                                                    "description": "Describe weekly routine.",
                                                    "stage": "intermediate",
                                                },
                                            ]
                                        }
                                    ),
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_topic_sequence(
                        language="ja",
                        fallback_topics=fallback_topics,
                    )
                )

                self.assertEqual(result.get("source"), "openai")
                topics = result.get("topics", [])
                self.assertEqual(len(topics), 3)
                self.assertEqual(topics[0]["stage"], "basic")
                self.assertEqual(topics[1]["stage"], "intermediate")
                self.assertEqual(topics[2]["stage"], "advanced")
                self.assertEqual(topics[0]["topic_key"], "basic_greetings")
                self.assertEqual(topics[2]["topic_key"], "future_hypotheticals")

    def test_generate_topic_sequence_falls_back_when_output_is_invalid(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            fallback_topics = [
                {
                    "topic_key": "identity_and_plans",
                    "title": "Identity and Daily Plans",
                    "description": "Fallback identity topic.",
                    "stage": "basic",
                }
            ]
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
                                    "text": '{"not_topics":[]}',
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_topic_sequence(
                        language="ja",
                        fallback_topics=fallback_topics,
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertEqual(result.get("topics"), fallback_topics)
                self.assertIn("Missing topics", result.get("error", ""))

    def test_generate_extra_game_prompt_falls_back_on_http_status_error(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            clear_cached_options()
            planner = OpenAIPlanner()
            with patch("languages.japanese.app.services.openai_client.httpx.AsyncClient") as mock_client:
                mock_http = mock_client.return_value.__aenter__.return_value
                mock_response = MagicMock()
                request = httpx.Request("POST", "https://api.openai.com/v1/responses")
                response = httpx.Response(
                    400,
                    request=request,
                    content=b'{"error":{"message":"invalid_request"}}',
                )
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "bad request",
                    request=request,
                    response=response,
                )
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_extra_game_prompt(
                        language="ja",
                        topic_title="Identity",
                        game_type="kana_speed_round",
                        level=1,
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertEqual(
                    result.get("text"),
                    "Topic: Identity. Try this kana_speed_round activity at level 1.",
                )
                self.assertIn("Extra game prompt request failed: HTTP 400", result.get("error", ""))

    def test_generate_extra_game_prompt_falls_back_when_output_is_empty(self) -> None:
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
                                    "text": "   ",
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_extra_game_prompt(
                        language="ja",
                        topic_title="Identity",
                        game_type="pronunciation_match",
                        level=2,
                    )
                )

                self.assertEqual(result.get("source"), "fallback")
                self.assertEqual(result.get("error"), "Empty extra game prompt output.")

    def test_generate_extra_game_prompt_uses_string_content_for_responses_input(self) -> None:
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
                                    "text": "Practice this sentence first.",
                                }
                            ]
                        }
                    ]
                }
                mock_http.post = AsyncMock(return_value=mock_response)

                result = asyncio.run(
                    planner.generate_extra_game_prompt(
                        language="ja",
                        topic_title="Identity",
                        game_type="sentence_order",
                        level=1,
                    )
                )

                self.assertEqual(result.get("source"), "openai")
                self.assertEqual(result.get("text"), "Practice this sentence first.")
                _, kwargs = mock_http.post.call_args
                payload = kwargs["json"]
                self.assertIn("input", payload)
                self.assertIsInstance(payload["input"], list)
                self.assertGreaterEqual(len(payload["input"]), 2)
                self.assertIsInstance(payload["input"][0]["content"], str)
                self.assertIsInstance(payload["input"][1]["content"], str)
                self.assertNotIsInstance(payload["input"][0]["content"], list)


if __name__ == "__main__":
    unittest.main()
