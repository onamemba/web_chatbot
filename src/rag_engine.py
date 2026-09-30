"""
Core RAG logic: embed the question, retrieve the most relevant chunks from
ChromaDB, then ask Groq's LLM to answer using ONLY that retrieved context.
Works for any knowledge base; behaviour is configured via .env.
"""

import os

import chromadb
from groq import Groq
from sentence_transformers import SentenceTransformer

from config import (
    BOT_NAME,
    BOT_SUBJECT,
    CHROMA_DB_DIR,
    COLLECTION_NAME,
    CONTACT,
    EMBEDDING_MODEL_NAME,
    GROQ_MODEL,
    TOP_K,
)

_fallback = f" and suggest they contact {CONTACT}" if CONTACT else ""

SYSTEM_PROMPT = f"""You are {BOT_NAME}, a helpful assistant that answers questions about {BOT_SUBJECT}.

Answer the user's question using ONLY the context provided below.

If the answer isn't in the context, say clearly that you don't have
that information{_fallback}. Never invent facts.

Keep answers concise and friendly.

Mention which source document the answer comes from when possible.
"""


class RAGEngine:
    def __init__(self):
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        self.collection = self.chroma_client.get_or_create_collection(name=COLLECTION_NAME)

        print(f"ChromaDB path: {CHROMA_DB_DIR}")
        print(f"Collection: {COLLECTION_NAME} ({self.collection.count()} chunks)")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get a free key at "
                "https://console.groq.com/keys and add it to your .env file."
            )
        self.groq_client = Groq(api_key=api_key)

    def retrieve(self, question: str, top_k: int = TOP_K):
        """Embed the question and return [(chunk, metadata), ...]."""
        total = self.collection.count()
        if total == 0:
            return []

        query_embedding = self.embedding_model.encode([question]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(top_k, total),
        )
        return list(zip(results["documents"][0], results["metadatas"][0]))

    def generate_answer(self, question: str, retrieved_chunks):
        """Generate an answer grounded only in the retrieved context."""
        if not retrieved_chunks:
            contact = f" Please contact {CONTACT}." if CONTACT else ""
            return f"My knowledge base is empty, so I can't answer that yet.{contact}"

        context_text = "\n\n---\n\n".join(
            f"[Source: {meta.get('source', 'unknown')}]\n{chunk}"
            for chunk, meta in retrieved_chunks
        )

        user_prompt = f"""Context from the knowledge base:

{context_text}

---

Question: {question}

Answer the question using only the context above.
"""

        response = self.groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return response.choices[0].message.content

    def ask(self, question: str):
        """Full RAG pipeline -> {"answer": str, "sources": [str]}."""
        retrieved = self.retrieve(question)
        answer = self.generate_answer(question, retrieved)
        sources = sorted({meta.get("source", "unknown") for _, meta in retrieved})
        return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    engine = RAGEngine()
    while True:
        q = input("\nAsk (blank to quit): ").strip()
        if not q:
            break
        result = engine.ask(q)
        print(f"A: {result['answer']}\nSources: {result['sources']}")
