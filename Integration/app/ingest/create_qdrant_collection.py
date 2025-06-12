import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = int(os.getenv("QDRANT_PORT"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
VECTOR_SIZE = 1024 

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def create_collection():
    existing = qdrant.get_collections().collections
    if COLLECTION_NAME in [col.name for col in existing]:
        print(f"[x] '{COLLECTION_NAME}' 이미 존재하는 컬렉션")
    else:
        qdrant.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )
        print(f"[✓] '{COLLECTION_NAME}' 생성 완료")

if __name__ == "__main__":
    create_collection()