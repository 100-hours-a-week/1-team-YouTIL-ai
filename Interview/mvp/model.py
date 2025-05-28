import os
import logging
from uuid import uuid4
from typing import Optional, List
from qdrant_client import QdrantClient
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class InterviewModels:
    def __init__(self):
        self.base_llm_path = os.getenv("MODEL2_PATH")
        self.qdrant_host = os.getenv("QDRANT_HOST")
        self.qdrant_port = os.getenv("QDRANT_PORT")
        self.embed_model_name = "BAAI/bge-m3"

        self.llm = self._load_llm()
        self.embedder = self._load_embedder()
        self.qdrant = self._load_qdrant()
    
    def _load_llm(self) -> AsyncLLMEngine:
        engine_args = AsyncEngineArgs(
            model=self.base_llm_path,
            tensor_parallel_size=1,
            gpu_memory_utilization=0.95,
            max_num_seqs=32,
            max_model_len=4096,
            max_num_batched_tokens=4096
        )
        return AsyncLLMEngine.from_engine_args(engine_args)

    def _load_embedder(self) -> SentenceTransformer:
        return SentenceTransformer(self.embed_model_name, device="cpu")

    def _load_qdrant(self) -> QdrantClient:
        return QdrantClient(
            host=self.qdrant_host,
            port=self.qdrant_port
        )

    async def generate(self, prompt: str, sampling_params: Optional[SamplingParams] = None) -> str:
        try:
            request_id = str(uuid4())
            result = ""
            async for output in self.llm.generate(
                prompt=prompt,
                sampling_params=sampling_params,
                request_id=request_id
            ):
                result = output.outputs[0].text.strip()
            return result
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