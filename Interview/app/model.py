import os
import logging
from uuid import uuid4
from typing import Optional, List
from qdrant_client import QdrantClient
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class InterviewModels:
    def __init__(self):
        self.base_llm_url = os.getenv("OPENAI_API_BASE")  
        self.api_key = os.getenv("OPENAI_API_KEY") 
        self.qdrant_host = os.getenv("QDRANT_HOST")
        self.qdrant_port = os.getenv("QDRANT_PORT")
        self.embed_model_name = "BAAI/bge-m3"

        self.llm = self._load_llm()
        self.embedder = self._load_embedder()
        self.qdrant = self._load_qdrant()
    
    def _load_llm(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self.base_llm_url,
            api_key=self.api_key
        )

    def _load_embedder(self) -> SentenceTransformer:
        return SentenceTransformer(self.embed_model_name, device="cpu")

    def _load_qdrant(self) -> QdrantClient:
        return QdrantClient(
            host=self.qdrant_host,
            port=self.qdrant_port
        )

    async def generate(self, 
                       prompt: str, 
                       max_tokens: int = 512,
                       temperature: float = 0.7) -> str:
        try:
            response = await self.llm.completions.create(
                model="google/gemma-3-4b-it",
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].text.strip()
        
        except Exception as e:
            logger.error(f"LLM 응답 실패: {e}")
            raise

    def embed_text(self, text: str) -> List[float]:
        try:
            return self.embedder.encode(text).tolist()
        except Exception as e:
            logger.error(f"임베딩 실패: {e}")
            raise

model = InterviewModels()