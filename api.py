"""
FastAPI backend for embedding the chatbot on ANY website.

Run with: uvicorn api:app --host 0.0.0.0 --port 8000
Demo page: http://localhost:8000/static/index.html
"""

import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent / "src"))
from config import ALLOWED_ORIGINS, BOT_NAME, RATE_LIMIT_PER_MIN, WELCOME_MESSAGE  # noqa: E402
from ingest import (  # noqa: E402
    SUPPORTED,
    delete_document,
    ingest_file,
    list_documents,
    max_upload_bytes,
    safe_upload_filename,
    upload_destination,
)
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
    allow_methods=["GET", "POST", "DELETE"],
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


@app.post("/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """Upload a document through the website and index it immediately."""
    check_rate_limit(request)

    try:
        filename = safe_upload_filename(file.filename or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    if Path(filename).suffix.lower() not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Use: {', '.join(sorted(SUPPORTED))}",
        )

    content = await file.read()
    if len(content) > max_upload_bytes():
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {max_upload_bytes() // (1024 * 1024)} MB.",
        )
    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty.")

    dest = upload_destination(filename)
    dest.write_bytes(content)

    try:
        chunks = ingest_file(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        print(f"Ingest error for {filename}: {e}")
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not index the document. Please try again.")

    return {"filename": filename, "chunks": chunks}


@app.get("/documents")
def documents(request: Request):
    """List indexed documents with their chunk counts."""
    check_rate_limit(request)
    return {"documents": list_documents()}


@app.delete("/documents/{filename}")
def delete_document_endpoint(filename: str, request: Request):
    """Remove a document's chunks from the index and delete its uploaded file."""
    check_rate_limit(request)

    try:
        safe_name = safe_upload_filename(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    removed = delete_document(safe_name)
    dest = upload_destination(safe_name)
    file_removed = dest.exists() and dest.is_file()
    if file_removed:
        dest.unlink()

    if removed == 0 and not file_removed:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {"filename": safe_name, "deleted": True}


# Serves widget/chat-widget.js and the demo page
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "widget"), name="static")
