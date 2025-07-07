import os
import logging
import google.generativeai as genai
from typing import List
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
        self.llm = self._load_llm()
        self.qdrant_host = os.getenv("QDRANT_HOST")
        self.qdrant_port = os.getenv("QDRANT_PORT")
        self.qdrant = self._load_qdrant()
        self.embed_model_name = "BAAI/bge-m3"
        self.embedder = self._load_embedder()
        self.vertex_api_key = os.getenv("VERTEX_API_KEY")
        self.gemini_model = self._load_gemini()

    def _load_llm(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self.base_llm_url,
            api_key=self.api_key
        )
    
    def _load_gemini(self):
        """Gemini 모델 초기화"""
        if self.vertex_api_key:
            genai.configure(api_key=self.vertex_api_key)
            return genai.GenerativeModel("gemini-1.5-flash")
        else:
            logger.warning("Gemini 호출 비활성화")
            
    async def generate_gemini (self,
                      prompt:str,
                      max_tokens: int,
                      temperature: float) -> str:
        """Gemmini 호출 메서드"""
        if not self.gemini_model:
            logger.warning("gemini 호출 실패로 Gemma 모델로 대체합니다.")
            return await self.generate(prompt, max_tokens, temperature)

        config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature
        )
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config = config
            )
            return response.text.strip()

        except Exception as e:
            err_msg = str(e)

            if "429" in err_msg or "quota" in err_msg.lower():
                logger.warning(f"🚨 Gemini 호출 실패 (quota 초과): {err_msg} → Gemma로 fallback")
                return await self.generate(prompt, max_tokens, temperature)

            logger.error(f"Gemini 호출 실패: {e}")
            raise

    async def generate(self, 
                       prompt: str, 
                       max_tokens: int = 512,
                       temperature: float = 0.3,) -> str:

        """Gemma 호출 메서드"""
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

    def _load_embedder(self) -> SentenceTransformer:
        return SentenceTransformer(self.embed_model_name, device="cpu")

    def _load_qdrant(self) -> QdrantClient:
        return QdrantClient(
            host=self.qdrant_host,
            port=self.qdrant_port
        )

    def embed_text(self, text: str) -> List[float]:
        try:
            return self.embedder.encode(text).tolist()
        except Exception as e:
            logger.error(f"임베딩 실패: {e}")
            raise

model = InterviewModels()