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

os.environ['LANGCHAIN-PROJECT'] = 'RAG CHATBOT'


# Load .env
load_dotenv()


PDF_PATH = "islr.pdf"


# =========================================================
# 1. LOAD PDF
# =========================================================

@traceable(name="load_pdf")
def load_pdf(path: str):
    loader = PyPDFLoader(path)
    return loader.load()


# =========================================================
# 2. SPLIT DOCUMENTS
# =========================================================

@traceable(name="split_documents")
def split_documents(docs, chunk_size=1000, chunk_overlap=150):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    return splitter.split_documents(docs)


# =========================================================
# 3. BUILD VECTOR STORE
# =========================================================

@traceable(name="build_vectorstore")
def build_vectorstore(splits):

    # Local Hugging Face embeddings
    emb = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # Create FAISS vector database
    vs = FAISS.from_documents(
        splits,
        emb
    )

    return vs


# =========================================================
# 4. SETUP PIPELINE
# =========================================================

@traceable(name="setup_pipeline")
def setup_pipeline(pdf_path: str):

    docs = load_pdf(pdf_path)

    splits = split_documents(docs)

    vs = build_vectorstore(splits)

    return vs


# =========================================================
# 5. GROQ LLM
# =========================================================

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)


# =========================================================
# 6. PROMPT
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
# 7. FORMAT DOCUMENTS
# =========================================================

def format_docs(docs):

    return "\n\n".join(
        d.page_content
        for d in docs
    )


# =========================================================
# 8. BUILD VECTOR DATABASE
# =========================================================

vectorstore = setup_pipeline(PDF_PATH)


# =========================================================
# 9. RETRIEVER
# =========================================================

retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 4
    }
)


# =========================================================
# 10. RETRIEVE CONTEXT + QUESTION
# =========================================================

parallel = RunnableParallel({

    "context": retriever | RunnableLambda(format_docs),

    "question": RunnablePassthrough()

})


# =========================================================
# 11. RAG CHAIN
# =========================================================

chain = (
    parallel
    | prompt
    | llm
    | StrOutputParser()
)


# =========================================================
# 12. ASK QUESTION
# =========================================================

print("PDF RAG ready. Ask a question (or Ctrl+C to exit).")

q = input("\nQ: ").strip()


# LangSmith configuration
config = {
    "run_name": "pdf_rag_query",
    "tags": ["groq", "rag", "pdf"],
    "metadata": {
        "model": "openai/gpt-oss-20b",
        "embedding_model": "all-MiniLM-L6-v2"
    }
}


# Run chain
ans = chain.invoke(
    q,
    config=config
)


print("\nA:", ans)