"""
Streamlit frontend (great for demos and internal use).
Run with: streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from config import BOT_NAME, BOT_SUBJECT, WELCOME_MESSAGE  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402

st.set_page_config(page_title=BOT_NAME, page_icon="💬", layout="centered")

st.title(f"💬 {BOT_NAME}")
st.caption(f"Ask me about {BOT_SUBJECT}. I only answer using the documents I've been given.")


@st.cache_resource
def load_engine():
    return RAGEngine()


try:
    engine = load_engine()
except ValueError as e:
    st.error(str(e))
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching the knowledge base..."):
            result = engine.ask(prompt)
            answer, sources = result["answer"], result["sources"]
            st.markdown(answer)
            if sources:
                st.caption(f"📄 Source: {', '.join(sources)}")

    full_response = answer + (f"\n\n*Source: {', '.join(sources)}*" if sources else "")
    st.session_state.messages.append({"role": "assistant", "content": full_response})

with st.sidebar:
    st.header("About this project")
    st.markdown(
        """
A Retrieval-Augmented Generation (RAG) chatbot that answers questions
using **your own documents**.

**How it works:**
1. Documents come from a local folder or **AWS S3**
2. They're chunked and embedded locally (free)
3. Embeddings are stored in **ChromaDB**
4. Your question is matched to the most relevant chunks
5. **Groq** generates an answer grounded in that context

**Stack:** Python · sentence-transformers · ChromaDB · Groq · Streamlit · FastAPI
        """
    )
    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
        st.rerun()
