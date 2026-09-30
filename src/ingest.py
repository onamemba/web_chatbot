"""
Ingestion: load documents (local folder or S3) -> chunk -> embed locally -> ChromaDB.

Run whenever your documents change:
    python src/ingest.py                # uses DATA_SOURCE from .env
    python src/ingest.py --source local
    python src/ingest.py --source s3
"""

import argparse
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config import (
    CHROMA_DB_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DATA_DIR,
    DATA_SOURCE,
    EMBEDDING_MODEL_NAME,
    PROJECT_ROOT,
    S3_PREFIX,
)

SUPPORTED = {".md", ".txt", ".pdf"}


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
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


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


def build_index(source: str = DATA_SOURCE):
    if source == "s3":
        from s3_utils import download_docs_from_s3

        print("Downloading documents from S3...")
        source_dir = str(PROJECT_ROOT / "data_from_s3")
        download_docs_from_s3(s3_prefix=S3_PREFIX, local_dir=source_dir)
    else:
        source_dir = str(PROJECT_ROOT / DATA_DIR)
        print(f"Using local directory: {source_dir}")

    documents = load_documents(source_dir)
    if not documents:
        raise SystemExit(f"No .md/.txt/.pdf documents found in {source_dir}")
    print(f"Loaded {len(documents)} document(s).")

    print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}' (runs locally)...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index documents into ChromaDB.")
    parser.add_argument("--source", choices=["local", "s3"], default=DATA_SOURCE)
    build_index(parser.parse_args().source)
