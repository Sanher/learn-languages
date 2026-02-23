import json
import os
import tempfile
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
