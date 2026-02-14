from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .game_engine import DailyGamePlanner, LearnerSnapshot
from .memory import ProgressMemory
from .services.elevenlabs_client import ElevenLabsService
from .services.openai_client import OpenAIPlanner

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
DB_PATH = os.getenv("JAPANESE_DB_PATH", str(BASE_DIR / "data" / "progress.db"))

app = FastAPI(title="Japanese Daily Trainer")
planner = DailyGamePlanner()
memory = ProgressMemory(DB_PATH)
openai_planner = OpenAIPlanner()
elevenlabs = ElevenLabsService()


class DailyRequest(BaseModel):
    learner_id: str
    note: str = ""


class SessionResult(BaseModel):
    learner_id: str
    accuracy: float
    streak_days: int
    games_done: list[str]


class PronunciationRequest(BaseModel):
    expected: str
    transcript: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/web/")
def web_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/web/{path:path}")
def web_assets(path: str) -> FileResponse:
    return FileResponse(WEB_DIR / path)


@app.post("/api/daily")
async def get_daily_plan(req: DailyRequest) -> dict:
    state = memory.load_or_create(req.learner_id)
    snapshot = LearnerSnapshot(
        learner_id=state.learner_id,
        streak_days=state.streak_days,
        recent_accuracy=state.recent_accuracy,
        recent_games=[g for g in state.recent_games_csv.split(",") if g],
    )

    games = planner.choose_games(snapshot, date.today())
    difficulty = planner.difficulty_for(snapshot)
    content = await openai_planner.generate_daily_content(
        difficulty=difficulty,
        games=games,
        learner_note=req.note,
    )

    return {
        "games": games,
        "difficulty": difficulty,
        "content": content,
    }


@app.post("/api/session/complete")
def save_session(req: SessionResult) -> dict:
    memory.save_session(
        learner_id=req.learner_id,
        streak_days=req.streak_days,
        recent_accuracy=req.accuracy,
        recent_games=req.games_done,
    )
    return {"saved": True}


@app.post("/api/pronunciation/evaluate")
async def evaluate_pronunciation(req: PronunciationRequest) -> dict:
    return await elevenlabs.evaluate_pronunciation(req.transcript, req.expected)
