"""
Core RAG logic: given a user question, retrieve the most relevant
document chunks from ChromaDB, then ask Groq's LLM (free tier) to
answer using only that retrieved context.
"""

import os
import chromadb
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

CHROMA_DB_DIR = "chroma_db"
COLLECTION_NAME = "company_policies"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
GROQ_MODEL = "openai/gpt-oss-20b"
TOP_K = 4  # how many chunks to retrieve per question

SYSTEM_PROMPT = """You are a helpful internal HR assistant for new employees.
Answer the user's question using ONLY the context provided below.
If the answer isn't in the context, say clearly that you don't have that
information and suggest they contact HR at hr@company.com.
Keep answers concise and friendly. Cite which policy document the answer
comes from when possible."""


class RAGEngine:
    def __init__(self):
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        self.collection = self.chroma_client.get_collection(COLLECTION_NAME)

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get a free key at https://console.groq.com/keys "
                "and add it to your .env file."
            )
        self.groq_client = Groq(api_key=groq_api_key)

    def retrieve(self, question: str, top_k: int = TOP_K):
        """Embed the question and pull the most similar chunks from ChromaDB."""
        query_embedding = self.embedding_model.encode([question]).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
        )

        chunks = results["documents"][0]
        metadatas = results["metadatas"][0]
        return list(zip(chunks, metadatas))

    def generate_answer(self, question: str, retrieved_chunks):
        """Build a grounded prompt from retrieved chunks and call the LLM."""
        context_blocks = []
        for chunk, meta in retrieved_chunks:
            source = meta.get("source", "unknown")
            context_blocks.append(f"[Source: {source}]\n{chunk}")

        context_text = "\n\n---\n\n".join(context_blocks)

        user_prompt = f"""Context from company policy documents:

{context_text}

---

Employee question: {question}

Answer the question using only the context above."""

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
        """Full RAG pipeline: retrieve relevant context, then generate an answer."""
        retrieved = self.retrieve(question)
        answer = self.generate_answer(question, retrieved)
        sources = sorted(set(meta["source"] for _, meta in retrieved))
        return {"answer": answer, "sources": sources}


if __name__ == "__main__":
    # Quick command-line test before wiring up the Streamlit UI.
    engine = RAGEngine()
    test_questions = [
        "How do I request PTO?",
        "What's the process for getting promoted?",
        "How much parental leave do I get?",
    ]
    for q in test_questions:
        print(f"\nQ: {q}")
        result = engine.ask(q)
        print(f"A: {result['answer']}")
        print(f"Sources: {result['sources']}")
