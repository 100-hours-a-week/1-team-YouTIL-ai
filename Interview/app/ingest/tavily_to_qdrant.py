from tavily import TavilyClient
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import uuid
import os

load_dotenv()

# 초기화
client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
qdrant = QdrantClient(host=os.getenv("QDRANT_HOST"), port=int(os.getenv("QDRANT_PORT")))
embedder = SentenceTransformer("BAAI/bge-m3")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

# 예시
QUERIES = [
    "FastAPI 에러 핸들링",
    "OAuth2 원리",
    "Redis pubsub 구조",
    "Docker와 Kubernetes 차이",
    "LangChain에서 RAG 구현 방법"
]

def embed(text: str) -> list[float]:
    return embedder.encode(text).tolist()

def search_and_store(query: str):
    print(f"[+] '{query}' 검색 중 ...")
    results = client.search(query=query, search_depth="advanced", include_answer=True)

    for i, result in enumerate(results["results"]):
        title = result.get("title", "")
        url = result.get("url", "")
        content = result.get("content", "")

        # 필터링
        if len(content) < 200:
            continue

        # 청킹
        chunks = text_splitter.split_text(content)
        doc_id = str(uuid.uuid4())

        points = []
        for idx, chunk in enumerate(chunks):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embed(chunk),
                    payload={
                        "title": title,
                        "text": chunk,
                        "source": url,
                        "query": query
                    }
                )
            )
            
        qdrant.upsert(collection_name=os.getenv("COLLECTION_NAME"), points=points)
        print(f"[+] '{title}' from Tavily inserted ({len(points)} chunks)")

if __name__ == "__main__":
    for query in QUERIES:
        try:
            search_and_store(query)
        except Exception as e:
            print(f"[!] Error in '{query}': {e}")
