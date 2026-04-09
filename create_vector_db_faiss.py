import os
import sqlite3
import time

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

from backend.config import GEMINI_EMBEDDING_MODEL

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "fudan_knowledge_base.db")
FAISS_DB_DIR = os.path.join(BASE_DIR, "faiss_index_business")
BATCH_SIZE = 50


def load_documents():
    connection = sqlite3.connect(SQLITE_DB_PATH)
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, title, publish_date, link, content, article_type, main_topic, tag_text
        FROM articles
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()
    connection.close()

    documents = []
    for row in tqdm(rows, desc="Loading business articles", unit="article"):
        text = (
            f"Title: {row[1]}\n"
            f"Date: {row[2]}\n"
            f"Type: {row[5] or ''}\n"
            f"Main Topic: {row[6] or ''}\n"
            f"Tags: {row[7] or ''}\n\n"
            f"{row[4]}"
        )
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "article_id": row[0],
                    "title": row[1],
                    "publish_date": row[2],
                    "link": row[3],
                    "source": "business",
                },
            )
        )
    return documents


def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        length_function=len,
    )
    return splitter.split_documents(documents)


def create_index(chunks):
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        fallback_keys = [
            item.strip()
            for item in os.environ.get("GEMINI_API_KEYS", "").split(",")
            if item.strip()
        ]
        google_api_key = fallback_keys[0] if fallback_keys else ""
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set")

    embeddings = GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=google_api_key,
        task_type="retrieval_document",
    )

    vectorstore = None
    for index in tqdm(range(0, len(chunks), BATCH_SIZE), desc="Building FAISS index", unit="batch"):
        batch = chunks[index : index + BATCH_SIZE]
        for attempt in range(3):
            try:
                if vectorstore is None:
                    vectorstore = FAISS.from_documents(
                        batch,
                        embeddings,
                        distance_strategy=DistanceStrategy.COSINE,
                    )
                else:
                    vectorstore.add_documents(batch)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)

    os.makedirs(FAISS_DB_DIR, exist_ok=True)
    vectorstore.save_local(FAISS_DB_DIR)


if __name__ == "__main__":
    create_index(split_documents(load_documents()))
