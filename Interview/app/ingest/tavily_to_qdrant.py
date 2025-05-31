import os
import re
import uuid
import urllib.parse
from dotenv import load_dotenv
from tavily import TavilyClient
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance
from langchain.text_splitter import RecursiveCharacterTextSplitter

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
qdrant = QdrantClient(host=os.getenv("QDRANT_HOST"), port=int(os.getenv("QDRANT_PORT")))
embedder = SentenceTransformer("BAAI/bge-m3")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
COLLECTION_NAME = "tavily_docs"

QUERIES = [
    "FastAPI 에러 처리 방법",
    "OAuth2 인증 흐름 이해",
    "Redis pubsub 구조 설명",
    "쿠버네티스란 무엇인가",
    "LangChain으로 RAG 구현",
    "RAG 개념"
]

def clean_markdown(text: str) -> str:
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # 이미지 제거
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)   # 링크 제거
    text = re.sub(r"#{1,6}\s*", "", text)        # 헤더 제거
    text = re.sub(r"[*\-•]\s*", "", text)        # 불릿 제거
    text = re.sub(r"\n{2,}", "\n", text)         # 줄바꿈 정리
    return text.strip()

def korean_ratio(text: str) -> float:
    total = len(text)
    korean = len(re.findall(r"[가-힣]", text))
    return korean / total if total > 0 else 0

# chunk-level 유효성 검사
def is_valid_chunk(chunk: str) -> bool:
    if len(chunk) < 400:
        return False
    if korean_ratio(chunk) < 0.2:
        return False
    if "import " in chunk and len(chunk.split()) < 50:
        return False
    return True

def embed(text: str) -> list[float]:
    return embedder.encode(text).tolist()

def search_and_store(query: str):
    print(f"[+] '{query}' 검색 중 ...")
    results = client.search(query=query, search_depth="advanced", include_answer=True)

    for result in results["results"]:
        title = result.get("title", "")
        url = result.get("url", "")
        content = result.get("content", "")

        clean_text = clean_markdown(content)
        chunks = text_splitter.split_text(clean_text)

        points = []
        for chunk in chunks:
            if not is_valid_chunk(chunk):
                continue
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embed(chunk),
                    payload={
                        "title": title,
                        "text": chunk,
                        "source": urllib.parse.unquote(url),
                        "query": query
                    }
                )
            )
        
        if points:
            qdrant.upsert(collection_name=os.getenv("COLLECTION_NAME"), points=points)
            print(f"[✓] '{title}' 업서트 완료 ({len(points)} chunks)")
        
        else:
            print(f"[!] '{title}'는 필터링되어 저장되지 않음")

if __name__ == "__main__":
    for query in QUERIES:
        try:
            search_and_store(query)
        except Exception as e:
            print(f"[!] Error in '{query}': {e}")
