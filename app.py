"""
Streamlit frontend for the company policy RAG chatbot.

Run with: streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from rag_engine import RAGEngine  # noqa: E402

st.set_page_config(page_title="Company HR Assistant", page_icon="💬", layout="centered")

st.title("💬 Company HR Assistant")
st.caption(
    "Ask me about PTO, leave of absence, promotions, onboarding, or remote work policy. "
    "I only answer using the company's actual policy documents."
)


@st.cache_resource
def load_engine():
    return RAGEngine()


try:
    engine = load_engine()
except ValueError as e:
    st.error(str(e))
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi! I'm your HR assistant. Ask me anything about PTO, leave, "
            "promotions, onboarding, or remote work policy.",
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question, e.g. 'How do I request PTO?'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Checking company policy..."):
            result = engine.ask(prompt)
            answer = result["answer"]
            sources = result["sources"]

            st.markdown(answer)
            if sources:
                st.caption(f"📄 Source: {', '.join(sources)}")

    full_response = answer
    if sources:
        full_response += f"\n\n*Source: {', '.join(sources)}*"
    st.session_state.messages.append({"role": "assistant", "content": full_response})

with st.sidebar:
    st.header("About this project")
    st.markdown(
        """
This is a Retrieval-Augmented Generation (RAG) chatbot that answers
employee questions using real company policy documents.

**How it works:**
1. Company policy docs are stored in **AWS S3**
2. Documents are chunked and embedded locally (free, no API cost)
3. Embeddings are stored in **ChromaDB** (vector database)
4. Your question is matched against the most relevant chunks
5. **Groq** (free-tier LLM) generates an answer grounded in that context

**Tech stack:** AWS S3 · Python · sentence-transformers · ChromaDB · Groq · Streamlit
        """
    )
    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()
