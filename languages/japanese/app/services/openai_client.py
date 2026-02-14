from __future__ import annotations

import os
from typing import Any

import httpx


class OpenAIPlanner:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    async def generate_daily_content(self, *, difficulty: int, games: list[str], learner_note: str) -> dict[str, Any]:
        if not self.api_key:
            return {
                "source": "fallback",
                "activities": [
                    {
                        "game": game,
                        "prompt": f"Nivel {difficulty}: ejercicio de {game} para japonés.",
                    }
                    for game in games
                ],
            }

        system_prompt = (
            "Eres un tutor de japonés. Genera actividades cortas, divertidas y progresivas. "
            "Devuelve JSON válido con clave 'activities'."
        )
        user_prompt = (
            f"Dificultad {difficulty}/10. Juegos: {games}. "
            f"Notas del alumno: {learner_note}."
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
