"""
Streamlit frontend (great for demos and internal use).
Run with: streamlit run app.py

Upload documents right here on the website — they are indexed immediately,
no sync step needed.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from config import BOT_NAME, BOT_SUBJECT, WELCOME_MESSAGE  # noqa: E402
from ingest import (  # noqa: E402
    SUPPORTED,
    delete_document,
    ingest_file,
    list_documents,
    max_upload_bytes,
    upload_destination,
)
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

# --- Document upload ---
st.subheader("📤 Add documents")
uploaded = st.file_uploader(
    "Upload .md, .txt or .pdf files",
    type=[ext.lstrip(".") for ext in sorted(SUPPORTED)],
    accept_multiple_files=True,
)
if uploaded:
    for uf in uploaded:
        content = uf.getvalue()
        if len(content) > max_upload_bytes():
            st.error(f"❌ {uf.name}: too large (max {max_upload_bytes() // (1024 * 1024)} MB).")
            continue
        try:
            dest = upload_destination(uf.name)
        except ValueError:
            st.error(f"❌ {uf.name}: invalid filename.")
            continue
        dest.write_bytes(content)
        with st.spinner(f"Indexing {dest.name}..."):
            try:
                chunks = ingest_file(dest)
            except Exception as e:  # noqa: BLE001
                dest.unlink(missing_ok=True)
                st.error(f"❌ {dest.name}: {e}")
                continue
        st.success(f"✅ {dest.name}: indexed {chunks} chunks.")
    st.rerun()

# --- Knowledge base ---
st.subheader("📚 Knowledge base")
docs = list_documents()
if not docs:
    st.info("No documents indexed yet. Upload some above to teach the chatbot.")
else:
    for doc in docs:
        col_name, col_btn = st.columns([4, 1])
        with col_name:
            st.write(f"📄 **{doc['filename']}** — {doc['chunks']} chunks")
        with col_btn:
            if st.button("Delete", key=f"del-{doc['filename']}"):
                delete_document(doc["filename"])
                dest = upload_destination(doc["filename"])
                if dest.exists():
                    dest.unlink()
                st.rerun()

st.divider()

# --- Chat ---
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
1. Upload documents **right here on the website**
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
