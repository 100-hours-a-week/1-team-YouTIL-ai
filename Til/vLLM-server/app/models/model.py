from functools import lru_cache
from openai import AsyncOpenAI
import logging
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class ModelConfig:
    GEMMA_PATH: str = os.getenv("GEMMA_MODEL_4B_PATH")

class TILModel:
    def __init__(self, config: ModelConfig = ModelConfig()):
        self.config = config

        # vLLM 서버에 연결
        self.client = AsyncOpenAI(
            base_url="http://localhost:8001/v1",  # docker-compose에서 8000으로 열었을 가능성 높음
            api_key=os.getenv("OPENAI_API_KEY")
        )

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

@lru_cache()
def get_til_model() -> TILModel:
    return TILModel()