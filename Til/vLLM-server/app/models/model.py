import uuid
from functools import lru_cache
from openai import AsyncOpenAI
import logging
import os

from typing import Optional, List
from dotenv import load_dotenv

from transformers import AutoTokenizer, AutoModel
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams

load_dotenv()

logger = logging.getLogger(__name__)

class ModelConfig:
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    GEMMA_PATH: str = os.getenv("GEMMA_MODEL_4B_PATH")


class TILModels:
    def __init__(self, config: ModelConfig = ModelConfig()):
        self.config = config

        # vLLM 서버에 연결
        self.client = AsyncOpenAI(
            base_url="http://localhost:8001/v1",  # docker-compose에서 8000으로 열었을 가능성 높음
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self._initialize_embedding()

    def _initialize_embedding(self):
        self.embedding_tokenizer = AutoTokenizer.from_pretrained(self.config.EMBEDDING_MODEL)
        self.embedding_model = AutoModel.from_pretrained(self.config.EMBEDDING_MODEL)
        self.embedding_model.eval()

    async def generate(self, prompt: str, sampling_params: Optional[dict] = None,  extra_body: Optional[dict] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            request_payload = {
                "model": "google/gemma-3-4b-it",  # 실제 model 이름 확인 필요(curl http://localhost:8001/v1/models)
                "messages": messages,
                "temperature": sampling_params.get("temperature", 0.1) if sampling_params else 0.7,
                "max_tokens": sampling_params.get("max_tokens", 1024) if sampling_params else 1024,
                "top_p": sampling_params.get("top_p", 0.95) if sampling_params else 0.95,
            }

            # extra_body가 있다면 추가
            if extra_body:
                request_payload["extra_body"] = extra_body

            response = await self.client.chat.completions.create(**request_payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[vLLM generate] 오류 발생: {e}")
            return "[LLM 호출 실패]"

    async def get_embedding(self, text: str) -> List[float]:
        try:
            inputs = self.embedding_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            outputs = self.embedding_model(**inputs)
            embeddings = outputs.last_hidden_state.mean(dim=1)
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            raise

    @property
    def embedding_dimension(self) -> int:
        return self.embedding_model.config.hidden_size


@lru_cache()
def get_til_model() -> TILModels:
    return TILModels()