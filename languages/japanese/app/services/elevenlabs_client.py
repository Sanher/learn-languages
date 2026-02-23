from __future__ import annotations

import httpx
from .runtime_config import get_setting


class ElevenLabsService:
    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self.api_key = api_key or get_setting(
            env_names=("ELEVENLABS_API_KEY",),
            option_names=("elevenlabs_api_key", "elevenlabs.key", "elevenlabs.api_key"),
            default="",
        )
        self.voice_id = voice_id or get_setting(
            env_names=("ELEVENLABS_VOICE_ID",),
            option_names=("elevenlabs_voice_id", "elevenlabs.voice_id", "elevenlabs.voice"),
            default="",
        )
        self.model_id = model_id or get_setting(
            env_names=("ELEVENLABS_MODEL_ID",),
            option_names=("elevenlabs_model_id", "elevenlabs.model_id", "elevenlabs.model"),
            default="eleven_multilingual_v2",
        )

    async def tts_japanese(self, text: str) -> bytes:
        if not self.api_key or not self.voice_id:
            return b""

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={
                    "xi-api-key": self.api_key,
                    "accept": "audio/mpeg",
                    "content-type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": self.model_id,
                    "voice_settings": {"stability": 0.4, "similarity_boost": 0.75},
                },
            )
            response.raise_for_status()
            return response.content

    async def evaluate_pronunciation(self, transcript: str, expected: str) -> dict:
        """Placeholder: compares recognized text with expected text.

        In production, send audio to ASR and score phonetic distance.
        """
        ratio = 1.0 if transcript.strip() == expected.strip() else 0.6
        return {
            "score": round(ratio * 100),
            "feedback": "Very good." if ratio > 0.9 else "Good base, review intonation and particles.",
        }
