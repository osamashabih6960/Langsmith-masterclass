import os
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


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

PDF_PATH = "islr.pdf"


# =========================================================
# LOAD PDF
# =========================================================

@traceable(name="load_pdf")
def load_pdf(path: str):

    loader = PyPDFLoader(path)

    return loader.load()


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
# BUILD VECTOR STORE
# =========================================================

@traceable(name="build_vectorstore")
def build_vectorstore(splits):

    # Local Hugging Face embedding model
    emb = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    return FAISS.from_documents(
        splits,
        emb
    )


# =========================================================
# PARENT SETUP FUNCTION
# =========================================================

@traceable(
    name="setup_pipeline",
    tags=["setup"]
)
def setup_pipeline(
    pdf_path: str,
    chunk_size=1000,
    chunk_overlap=150
):

    # Load PDF
    docs = load_pdf(pdf_path)

    # Split documents
    splits = split_documents(
        docs,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    # Build vector database
    vs = build_vectorstore(splits)

    return vs


# =========================================================
# GROQ MODEL
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
# ROOT / TOP-LEVEL RUN
# =========================================================

@traceable(
    name="pdf_rag_full_run"
)
def setup_pipeline_and_query(
    pdf_path: str,
    question: str
):

    # -----------------------------------------------------
    # Setup pipeline
    # -----------------------------------------------------

    vectorstore = setup_pipeline(
        pdf_path,
        chunk_size=1000,
        chunk_overlap=150
    )

    # -----------------------------------------------------
    # Retriever
    # -----------------------------------------------------

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 4
        }
    )

    # -----------------------------------------------------
    # Retrieve context + question
    # -----------------------------------------------------

    parallel = RunnableParallel({
        "context": retriever | RunnableLambda(format_docs),
        "question": RunnablePassthrough(),
    })

    # -----------------------------------------------------
    # RAG chain
    # -----------------------------------------------------

    chain = (
        parallel
        | prompt
        | llm
        | StrOutputParser()
    )

    # -----------------------------------------------------
    # LangSmith config
    # -----------------------------------------------------

    lc_config = {
        "run_name": "pdf_rag_query"
    }

    # -----------------------------------------------------
    # Run
    # -----------------------------------------------------

    return chain.invoke(
        question,
        config=lc_config
    )


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":

    print(
        "PDF RAG ready. Ask a question "
        "(or Ctrl+C to exit)."
    )

    q = input("\nQ: ").strip()

    ans = setup_pipeline_and_query(
        PDF_PATH,
        q
    )

    print("\nA:", ans)