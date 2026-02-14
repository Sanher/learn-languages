from __future__ import annotations

import os

import httpx


class ElevenLabsService:
    def __init__(self, api_key: str | None = None, voice_id: str | None = None) -> None:
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")

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
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.4, "similarity_boost": 0.75},
                },
            )
            response.raise_for_status()
            return response.content

    async def evaluate_pronunciation(self, transcript: str, expected: str) -> dict:
        """Placeholder: compara texto reconocido con esperado.

        Para producción se recomienda enviar audio a ASR y luego medir distancia fonética.
        """
        ratio = 1.0 if transcript.strip() == expected.strip() else 0.6
        return {
            "score": round(ratio * 100),
            "feedback": "Muy bien" if ratio > 0.9 else "Buena base, revisa entonación y partículas.",
        }
