"""
Generic Retrieval-Augmented Generation engine.

Retrieves relevant document chunks from ChromaDB
and generates an answer using an LLM.
"""

import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "documents"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

GROQ_MODEL = "openai/gpt-oss-20b"

TOP_K = 4


DEFAULT_SYSTEM_PROMPT = """
You are a helpful AI assistant.

Answer the user's question using ONLY the information
contained in the provided context.

If the answer cannot be found in the context, clearly
say that the information is not available in the
provided documents.

Do not invent facts.

Keep answers clear, concise, and helpful.

When possible, mention the source document used.
"""


class RAGEngine:

    def __init__(
        self,
        collection_name=COLLECTION_NAME,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
    ):

        self.system_prompt = system_prompt

        # Embedding model
        self.embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

        # ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR)
        )

        self.collection = (
            self.chroma_client.get_or_create_collection(
                name=collection_name
            )
        )

        # Groq
        groq_api_key = os.getenv("GROQ_API_KEY")

        if not groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured."
            )

        self.groq_client = Groq(
            api_key=groq_api_key
        )

    def retrieve(
        self,
        question: str,
        top_k: int = TOP_K,
    ):

        document_count = self.collection.count()

        if document_count == 0:
            return []

        query_embedding = (
            self.embedding_model
            .encode([question])
            .tolist()
        )

        n_results = min(
            top_k,
            document_count
        )

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        return list(
            zip(documents, metadatas)
        )

    def generate_answer(
        self,
        question,
        retrieved_chunks,
    ):

        if not retrieved_chunks:
            return {
                "answer": (
                    "I couldn't find information "
                    "about that in the available documents."
                ),
                "sources": [],
            }

        context_blocks = []

        for chunk, metadata in retrieved_chunks:

            source = metadata.get(
                "source",
                "unknown"
            )

            context_blocks.append(
                f"[Source: {source}]\n{chunk}"
            )

        context = "\n\n---\n\n".join(
            context_blocks
        )

        prompt = f"""
Context:

{context}

---

User question:

{question}

Answer using only the context above.
"""

        response = (
            self.groq_client
            .chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompt,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )
        )

        answer = (
            response
            .choices[0]
            .message
            .content
        )

        sources = sorted(
            set(
                metadata.get(
                    "source",
                    "unknown"
                )
                for _, metadata
                in retrieved_chunks
            )
        )

        return {
            "answer": answer,
            "sources": sources,
        }

    def ask(self, question):

        retrieved = self.retrieve(question)

        return self.generate_answer(
            question,
            retrieved
        )