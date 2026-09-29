"""
Ingestion pipeline: pulls documents from S3, chunks them, embeds them
with a local (free) embedding model, and stores the vectors in ChromaDB.

Run this once (or whenever your source documents change) before
querying the chatbot.
"""

import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from s3_utils import download_docs_from_s3

CHROMA_DB_DIR = "chroma_db"
COLLECTION_NAME = "company_policies"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # small, fast, free, runs locally
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 150  # overlap between chunks to preserve context across boundaries
S3_PREFIX = "hr-policy/data/"  # matches s3://rag-chatbot-data-bkt/hr-policy/data/*.md


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Simple sliding-window chunker. Good enough for short policy docs."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def load_documents(local_dir: str):
    """Read all .md/.txt files from a local directory into memory."""
    documents = []
    for file_path in Path(local_dir).glob("*"):
        if file_path.suffix in (".md", ".txt"):
            text = file_path.read_text(encoding="utf-8")
            documents.append({"filename": file_path.name, "text": text})
    return documents


def build_index(use_s3: bool = True):
    """
    Full ingestion run:
      1. Pull docs from S3 (or use local ./data if use_s3=False)
      2. Chunk each doc
      3. Embed each chunk locally (sentence-transformers, no API cost)
      4. Store embeddings + text + metadata in ChromaDB
    """
    if use_s3:
        print("Downloading documents from S3...")
        download_docs_from_s3(s3_prefix=S3_PREFIX, local_dir="data_from_s3")
        source_dir = "data_from_s3"
    else:
        print("Using local ./data directory (S3 skipped).")
        source_dir = "data"

    documents = load_documents(source_dir)
    print(f"Loaded {len(documents)} documents.")

    print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}' (runs locally, free)...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    # Fresh collection each run, keeps this idempotent and simple.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    all_chunks = []
    all_metadatas = []
    all_ids = []
    chunk_counter = 0

    for doc in documents:
        chunks = chunk_text(doc["text"])
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({"source": doc["filename"], "chunk_index": i})
            all_ids.append(f"chunk-{chunk_counter}")
            chunk_counter += 1

    print(f"Created {len(all_chunks)} chunks. Embedding now...")
    embeddings = model.encode(all_chunks, show_progress_bar=True).tolist()

    collection.add(
        ids=all_ids,
        embeddings=embeddings,
        documents=all_chunks,
        metadatas=all_metadatas,
    )

    print(f"Done. Indexed {len(all_chunks)} chunks into ChromaDB at '{CHROMA_DB_DIR}'.")


if __name__ == "__main__":
    # Set use_s3=False for a quick local-only test without touching AWS.
    build_index(use_s3=True)