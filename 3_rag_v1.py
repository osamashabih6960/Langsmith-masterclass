import os
from dotenv import load_dotenv

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

load_dotenv()

PDF_PATH = "islr.pdf"


# 1) Load PDF
loader = PyPDFLoader(PDF_PATH)
docs = loader.load()


# 2) Split PDF into chunks
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150
)

splits = splitter.split_documents(docs)

print(f"Loaded {len(docs)} pages")
print(f"Created {len(splits)} chunks")


# 3) Create embeddings
emb = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


# 4) Create FAISS vector database
vs = FAISS.from_documents(
    splits,
    emb
)

retriever = vs.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 4}
)


# 5) Prompt
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """Answer ONLY from the provided context.
If the answer is not found in the context, say you don't know."""
    ),
    (
        "human",
        """Question: {question}

Context:
{context}"""
    )
])


# 6) Groq LLM
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)


# 7) Format retrieved documents
def format_docs(docs):
    return "\n\n".join(
        doc.page_content
        for doc in docs
    )


# 8) Retrieve context + question
parallel = RunnableParallel({
    "context": retriever | RunnableLambda(format_docs),
    "question": RunnablePassthrough()
})


# 9) RAG Chain
chain = (
    parallel
    | prompt
    | llm
    | StrOutputParser()
)


# 10) Ask questions
print("\nPDF RAG ready. Ask a question (or Ctrl+C to exit).")

q = input("\nQ: ")

ans = chain.invoke(q.strip())

print("\nA:", ans)