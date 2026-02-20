from __future__ import annotations

import os
from typing import Any

import httpx


class OpenAIPlanner:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        raw_stt_models = os.getenv("OPENAI_STT_MODELS", "gpt-4o-mini-transcribe,whisper-1")
        self.stt_models = [model_name.strip() for model_name in raw_stt_models.split(",") if model_name.strip()]

    async def generate_daily_content(self, *, difficulty: int, games: list[str], learner_note: str) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": "fallback",
                "activities": [
                    {
                        "game": game,
                        "prompt": f"Level {difficulty}: {game} exercise for Japanese.",
                    }
                    for game in games
                ],
            }

        system_prompt = (
            "You are a Japanese tutor. Generate short, fun, progressive activities. "
            "Return valid JSON with key 'activities'."
        )
        user_prompt = (
            f"Difficulty {difficulty}/10. Games: {games}. "
            f"Learner notes: {learner_note}."
        )

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
                    ],
                    "text": {"format": {"type": "json_object"}},
                },
            )
            response.raise_for_status()
            payload = response.json()

        text_outputs = payload.get("output", [])
        content_text = ""
        for block in text_outputs:
            for item in block.get("content", []):
                if item.get("type") == "output_text":
                    content_text += item.get("text", "")

        return {
            "source": "openai",
            "raw": content_text,
        }

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        mime_type: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": "fallback",
                "transcript": "",
                "error": "OPENAI_API_KEY is not configured for STT.",
            }

        if not audio_bytes:
            return {
                "source": "fallback",
                "transcript": "",
                "error": "Empty audio payload.",
            }

        errors: list[str] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for stt_model in self.stt_models:
                data: dict[str, str] = {"model": stt_model}
                if language:
                    data["language"] = language
                files = {
                    "file": (filename, audio_bytes, mime_type),
                }
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        data=data,
                        files=files,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    transcript = (payload.get("text") or payload.get("transcript") or "").strip()
                    return {
                        "source": "openai",
                        "model": stt_model,
                        "transcript": transcript,
                    }
                except httpx.HTTPStatusError as exc:
                    errors.append(f"{stt_model}: HTTP {exc.response.status_code}")
                except Exception as exc:  # pragma: no cover - defensive for network/provider edge cases
                    errors.append(f"{stt_model}: {type(exc).__name__}")

        return {
            "source": "fallback",
            "transcript": "",
            "error": "Audio transcription failed.",
            "details": errors,
        }
