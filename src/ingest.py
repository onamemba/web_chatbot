"""
Ingestion: load documents (local folder or website upload) -> chunk -> embed locally -> ChromaDB.

Bulk CLI build (wipe and rebuild the whole index from a folder):
    python src/ingest.py                  # uses DATA_DIR
    python src/ingest.py --data-dir data/uploads

Live website uploads go through ingest_file() instead (idempotent per document).
"""

import argparse
import uuid
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config import (
    CHROMA_DB_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DATA_DIR,
    EMBEDDING_MODEL_NAME,
    MAX_UPLOAD_MB,
    PROJECT_ROOT,
    UPLOAD_DIR,
)

SUPPORTED = {".md", ".txt", ".pdf"}

_model = None
_client = None


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Sliding-window chunker with overlap to preserve context across boundaries."""
    step = max(1, chunk_size - overlap)
    chunks = []
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def read_file(path: Path) -> str:
    """Read .md / .txt / .pdf into plain text."""
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def get_embedding_model() -> SentenceTransformer:
    """Lazy singleton: the embedding model is heavy to load, so load it once."""
    global _model
    if _model is None:
        print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}' (runs locally)...")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_collection():
    """Lazy singleton ChromaDB collection (created if missing)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    return _client.get_or_create_collection(name=COLLECTION_NAME)


def delete_document(filename: str) -> int:
    """Remove every chunk whose metadata source == filename. Returns chunks removed."""
    collection = get_collection()
    existing = collection.get(where={"source": filename}, include=[], limit=1)
    if not existing["ids"]:
        return 0
    collection.delete(where={"source": filename})
    return len(existing["ids"])


def ingest_text(filename: str, text: str) -> int:
    """
    Chunk + embed + upsert one document into ChromaDB.

    Idempotent per filename: any existing chunks with metadata
    source == filename are deleted first. Returns the number of chunks added.
    """
    collection = get_collection()
    delete_document(filename)

    chunks = chunk_text(text)
    if not chunks:
        return 0

    model = get_embedding_model()
    embeddings = model.encode(chunks, show_progress_bar=False).tolist()

    tag = uuid.uuid4().hex[:8]
    ids = [f"{filename}::{tag}::{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

    batch = 500
    for i in range(0, len(chunks), batch):
        collection.add(
            ids=ids[i : i + batch],
            embeddings=embeddings[i : i + batch],
            documents=chunks[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )
    return len(chunks)


def ingest_file(path: Path) -> int:
    """Read a file from disk and ingest it. Returns the number of chunks added."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {path.suffix} (use .md, .txt, .pdf)")
    text = read_file(path).strip()
    if not text:
        raise ValueError(f"No readable text found in {path.name}")
    return ingest_text(path.name, text)


def list_documents() -> list[dict]:
    """Return [{"filename": str, "chunks": int}] for every indexed document."""
    collection = get_collection()
    rows = collection.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in rows["metadatas"]:
        source = (meta or {}).get("source", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return [{"filename": name, "chunks": n} for name, n in sorted(counts.items())]


def load_documents(local_dir: str):
    """Recursively read .md / .txt / .pdf files into memory."""
    base = Path(local_dir)
    documents = []
    for fp in sorted(base.rglob("*")):
        if fp.is_file() and fp.suffix.lower() in SUPPORTED:
            text = read_file(fp).strip()
            if text:
                documents.append({"filename": str(fp.relative_to(base)), "text": text})
    return documents


def build_index(data_dir: str):
    """Wipe and rebuild the whole index from a local folder (CLI bulk path)."""
    source_dir = str(PROJECT_ROOT / data_dir) if not Path(data_dir).is_absolute() else data_dir
    print(f"Using local directory: {source_dir}")

    documents = load_documents(source_dir)
    if not documents:
        raise SystemExit(f"No .md/.txt/.pdf documents found in {source_dir}")
    print(f"Loaded {len(documents)} document(s).")

    model = get_embedding_model()

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)  # fresh index each run (idempotent)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    chunks, metadatas, ids = [], [], []
    for doc in documents:
        for i, chunk in enumerate(chunk_text(doc["text"])):
            chunks.append(chunk)
            metadatas.append({"source": doc["filename"], "chunk_index": i})
            ids.append(f"chunk-{len(ids)}")

    print(f"Created {len(chunks)} chunks. Embedding...")
    embeddings = model.encode(chunks, show_progress_bar=True).tolist()

    batch = 500
    for i in range(0, len(chunks), batch):
        collection.add(
            ids=ids[i : i + batch],
            embeddings=embeddings[i : i + batch],
            documents=chunks[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )

    print(f"Done. Indexed {len(chunks)} chunks into '{COLLECTION_NAME}' at {CHROMA_DB_DIR}.")


def safe_upload_filename(name: str) -> str:
    """
    Sanitize an uploaded filename: strip directories, reject empty/traversal names,
    allow only a safe character set. Raises ValueError on invalid input.
    """
    cleaned = Path(name or "").name.strip().replace("\x00", "")
    cleaned = "".join(c for c in cleaned if c.isalnum() or c in "._- ()").strip().strip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Invalid filename")
    return cleaned


def upload_destination(filename: str) -> Path:
    """Resolve a sanitized filename inside UPLOAD_DIR (guards against traversal)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = (UPLOAD_DIR / safe_upload_filename(filename)).resolve()
    if dest.parent != UPLOAD_DIR.resolve():
        raise ValueError("Invalid filename")
    return dest


def max_upload_bytes() -> int:
    return MAX_UPLOAD_MB * 1024 * 1024


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index documents into ChromaDB.")
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args()
    build_index(args.data_dir)
