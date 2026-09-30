"""Central settings. Everything is driven by environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or default


# Identity: what this chatbot is about
BOT_NAME = _get("BOT_NAME", "AI Assistant")
BOT_SUBJECT = _get("BOT_SUBJECT", "the provided documents")
CONTACT = _get("CONTACT", "")
WELCOME_MESSAGE = _get(
    "WELCOME_MESSAGE", "Hi! Ask me anything."
)

# Data
DATA_SOURCE = _get("DATA_SOURCE", "local")  # local | s3
DATA_DIR = _get("DATA_DIR", "data")
S3_BUCKET_NAME = _get("S3_BUCKET_NAME", "")
S3_PREFIX = _get("S3_PREFIX", "")
AWS_REGION = _get("AWS_REGION", "us-east-1")

# Models / retrieval
GROQ_MODEL = _get("GROQ_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL_NAME = _get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME = _get("COLLECTION_NAME", "knowledge_base")
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
TOP_K = int(_get("TOP_K", "4"))
CHUNK_SIZE = int(_get("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(_get("CHUNK_OVERLAP", "150"))

# Website embedding
ALLOWED_ORIGINS = [o.strip() for o in _get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
RATE_LIMIT_PER_MIN = int(_get("RATE_LIMIT_PER_MIN", "20"))
