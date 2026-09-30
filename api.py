"""
FastAPI backend for embedding the chatbot on ANY website.

Run with: uvicorn api:app --host 0.0.0.0 --port 8000
Demo page: http://localhost:8000/static/demo.html
"""

import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent / "src"))
from config import ALLOWED_ORIGINS, BOT_NAME, RATE_LIMIT_PER_MIN, WELCOME_MESSAGE  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402

state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["engine"] = RAGEngine()  # load models once at startup
    yield


app = FastAPI(title=f"{BOT_NAME} API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# --- Basic in-memory rate limiting (per client IP) ---
_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    window.append(now)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health():
    return {"status": "ok", "chunks": state["engine"].collection.count()}


@app.get("/config")
def config():
    """Public settings the widget uses for its title and greeting."""
    return {"bot_name": BOT_NAME, "welcome_message": WELCOME_MESSAGE}


@app.post("/chat")
def chat(body: ChatRequest, request: Request):
    check_rate_limit(request)
    try:
        return state["engine"].ask(body.message.strip())
    except Exception as e:  # noqa: BLE001
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


# Serves widget/chat-widget.js and the demo page
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "widget"), name="static")
