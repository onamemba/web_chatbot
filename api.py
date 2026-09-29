"""
Generic RAG API.

Run with:

uvicorn api:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.rag_engine import RAGEngine


app = FastAPI(
    title="Generic RAG API",
    description="API for document-based AI question answering",
    version="1.0.0",
)


# Allow websites to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Load RAG engine once
engine = RAGEngine()


class ChatRequest(BaseModel):

    question: str


class ChatResponse(BaseModel):

    answer: str
    sources: list[str]


@app.get("/")
def root():

    return {
        "status": "online",
        "service": "Generic RAG API",
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "documents": engine.collection.count(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    result = engine.ask(
        request.question
    )

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
    )