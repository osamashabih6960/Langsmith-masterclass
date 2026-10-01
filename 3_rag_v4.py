import os
import json
import hashlib
from pathlib import Path
from dotenv import load_dotenv

from langsmith import traceable

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from langchain_groq import ChatGroq

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda
)
from langchain_core.output_parsers import StrOutputParser


load_dotenv()


# =========================================================
# CONFIG
# =========================================================

PDF_PATH = "islr.pdf"

INDEX_ROOT = Path(".indices")
INDEX_ROOT.mkdir(exist_ok=True)

# Local Hugging Face embedding model
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


# =========================================================
# LOAD PDF
# =========================================================

@traceable(name="load_pdf")
def load_pdf(path: str):

    return PyPDFLoader(path).load()


# =========================================================
# SPLIT DOCUMENTS
# =========================================================

@traceable(name="split_documents")
def split_documents(
    docs,
    chunk_size=1000,
    chunk_overlap=150
):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    return splitter.split_documents(docs)


# =========================================================
# BUILD VECTORSTORE
# =========================================================

@traceable(name="build_vectorstore")
def build_vectorstore(
    splits,
    embed_model_name: str
):

    emb = HuggingFaceEmbeddings(
        model_name=embed_model_name
    )

    return FAISS.from_documents(
        splits,
        emb
    )


# =========================================================
# FILE FINGERPRINT
# =========================================================

def _file_fingerprint(path: str) -> dict:

    p = Path(path)

    h = hashlib.sha256()

    with p.open("rb") as f:

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):
            h.update(chunk)

    return {
        "sha256": h.hexdigest(),
        "size": p.stat().st_size,
        "mtime": int(p.stat().st_mtime)
    }


# =========================================================
# INDEX KEY
# =========================================================

def _index_key(
    pdf_path: str,
    chunk_size: int,
    chunk_overlap: int,
    embed_model_name: str
) -> str:

    meta = {
        "pdf_fingerprint": _file_fingerprint(pdf_path),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embedding_model": embed_model_name,
        "format": "v2"
    }

    return hashlib.sha256(
        json.dumps(
            meta,
            sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


# =========================================================
# LOAD EXISTING INDEX
# =========================================================

@traceable(
    name="load_index",
    tags=["index"]
)
def load_index_run(
    index_dir: Path,
    embed_model_name: str
):

    emb = HuggingFaceEmbeddings(
        model_name=embed_model_name
    )

    return FAISS.load_local(
        str(index_dir),
        emb,
        allow_dangerous_deserialization=True
    )


# =========================================================
# BUILD NEW INDEX
# =========================================================

@traceable(
    name="build_index",
    tags=["index"]
)
def build_index_run(
    pdf_path: str,
    index_dir: Path,
    chunk_size: int,
    chunk_overlap: int,
    embed_model_name: str
):

    # Load PDF
    docs = load_pdf(pdf_path)

    # Split PDF
    splits = split_documents(
        docs,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    # Create embeddings + FAISS
    vs = build_vectorstore(
        splits,
        embed_model_name
    )

    # Create directory
    index_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save FAISS index
    vs.save_local(
        str(index_dir)
    )

    # Save metadata
    (index_dir / "meta.json").write_text(
        json.dumps(
            {
                "pdf_path": os.path.abspath(pdf_path),
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "embedding_model": embed_model_name
            },
            indent=2
        )
    )

    return vs


# =========================================================
# LOAD OR BUILD INDEX
# =========================================================

def load_or_build_index(
    pdf_path: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    embed_model_name: str = EMBED_MODEL_NAME,
    force_rebuild: bool = False
):

    key = _index_key(
        pdf_path,
        chunk_size,
        chunk_overlap,
        embed_model_name
    )

    index_dir = INDEX_ROOT / key

    cache_hit = (
        index_dir.exists()
        and not force_rebuild
    )

    if cache_hit:

        print("Loading existing FAISS index...")

        return load_index_run(
            index_dir,
            embed_model_name
        )

    else:

        print("Building new FAISS index...")

        return build_index_run(
            pdf_path,
            index_dir,
            chunk_size,
            chunk_overlap,
            embed_model_name
        )


# =========================================================
# GROQ LLM
# =========================================================

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)


# =========================================================
# PROMPT
# =========================================================

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Answer ONLY from the provided context. "
        "If not found, say you don't know."
    ),
    (
        "human",
        "Question: {question}\n\nContext:\n{context}"
    )
])


# =========================================================
# FORMAT DOCUMENTS
# =========================================================

def format_docs(docs):

    return "\n\n".join(
        d.page_content
        for d in docs
    )


# =========================================================
# SETUP PIPELINE
# =========================================================

@traceable(
    name="setup_pipeline",
    tags=["setup"]
)
def setup_pipeline(
    pdf_path: str,
    chunk_size=1000,
    chunk_overlap=150,
    embed_model_name=EMBED_MODEL_NAME,
    force_rebuild=False
):

    return load_or_build_index(
        pdf_path=pdf_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_model_name=embed_model_name,
        force_rebuild=force_rebuild
    )


# =========================================================
# COMPLETE RAG RUN
# =========================================================

@traceable(
    name="pdf_rag_full_run"
)
def setup_pipeline_and_query(
    pdf_path: str,
    question: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    embed_model_name: str = EMBED_MODEL_NAME,
    force_rebuild: bool = False
):

    # Get vector database
    vectorstore = setup_pipeline(
        pdf_path,
        chunk_size,
        chunk_overlap,
        embed_model_name,
        force_rebuild
    )

    # Retriever
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 4
        }
    )

    # Context + question
    parallel = RunnableParallel({

        "context": (
            retriever
            | RunnableLambda(format_docs)
        ),

        "question": RunnablePassthrough()
    })

    # RAG chain
    chain = (
        parallel
        | prompt
        | llm
        | StrOutputParser()
    )

    # Run
    return chain.invoke(
        question,
        config={
            "run_name": "pdf_rag_query",
            "tags": ["qa", "groq", "rag"],
            "metadata": {
                "k": 4,
                "llm": "openai/gpt-oss-20b",
                "embedding": embed_model_name
            }
        }
    )


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":

    print(
        "PDF RAG ready. "
        "Ask a question (or Ctrl+C to exit)."
    )

    q = input("\nQ: ").strip()

    ans = setup_pipeline_and_query(
        PDF_PATH,
        q
    )

    print("\nA:", ans)