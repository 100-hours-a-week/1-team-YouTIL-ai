import uuid
from functools import lru_cache
import logging
import os
from typing import Optional, List
from dotenv import load_dotenv

from transformers import AutoTokenizer, AutoModel
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams

load_dotenv()

logger = logging.getLogger(__name__)

class ModelConfig:
    GEMMA_PATH: str = os.getenv("GEMMA_MODEL_4B_PATH")
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    
    # VLLM 설정
    TENSOR_PARALLEL_SIZE: int = 1
    GPU_MEMORY_UTILIZATION: float = 0.95
    MAX_NUM_SEQS: int = 25
    MAX_MODEL_LEN: int = 4096
    MAX_NUM_BATCHED_TOKENS: int = 4096

class TILModels:
    def __init__(self, config: ModelConfig = ModelConfig()):
        self.config = config
        self._initialize_models()
        
    def _initialize_models(self):
        """임베딩 모델과 LLM 초기화"""
        try:
            # 임베딩 모델 초기화
            self.embedding_tokenizer = AutoTokenizer.from_pretrained(self.config.EMBEDDING_MODEL)
            self.embedding_model = AutoModel.from_pretrained(self.config.EMBEDDING_MODEL)
            self.embedding_model.eval()
            
            # VLLM 엔진 초기화
            engine_args = AsyncEngineArgs(
                model=self.config.GEMMA_PATH,
                tensor_parallel_size=self.config.TENSOR_PARALLEL_SIZE,
                gpu_memory_utilization=self.config.GPU_MEMORY_UTILIZATION,
                max_num_seqs=self.config.MAX_NUM_SEQS,
                max_model_len=self.config.MAX_MODEL_LEN,
                max_num_batched_tokens=self.config.MAX_NUM_BATCHED_TOKENS
            )
            
            self.llm = AsyncLLMEngine.from_engine_args(engine_args)
            
            logger.info("모델 초기화 완료")
            
        except Exception as e:
            logger.error(f"모델 초기화 실패: {e}")
            raise
    
    async def generate(self, prompt: str, sampling_params: Optional[SamplingParams] = None
) -> str:
        """LLM을 사용하여 텍스트 생성"""
        try:
            request_id = str(uuid.uuid4())
            
            async for output in self.llm.generate(
                prompt=prompt,
                sampling_params=sampling_params,
                request_id=request_id
            ):
                text_chunk = output.outputs[0].text
                full_text = text_chunk  # 보통 vLLM은 이전까지 누적된 전체 텍스트를 반환

            if not full_text:
                raise ValueError("생성된 출력이 없습니다.")

            return full_text

        except Exception as e:
            logger.error(f"텍스트 생성 실패: {e}")
            raise
    
    async def generate_til(self, prompt: str, sampling_params: Optional[SamplingParams] = None
) -> str:
        """TIL 생성을 위한 래퍼 메소드"""
        try:
            result = await self.generate(prompt, sampling_params)
            return result
        except Exception as e:
            logger.error(f"TIL 생성 실패: {e}")
            return "[LLM 호출 실패]"

    async def get_embedding(self, text: str) -> List[float]:
        """텍스트의 임베딩 벡터를 반환합니다."""
        try:
            inputs = self.embedding_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            outputs = self.embedding_model(**inputs)
            embeddings = outputs.last_hidden_state.mean(dim=1)  # [1, hidden_size]
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            raise

    @property
    def embedding_dimension(self) -> int:
        """임베딩 벡터의 차원을 반환합니다."""
        return self.embedding_model.config.hidden_size

# 모델은 요청이 있을 때, 처음으로 로딩함 -> 그 이후에는 요청 즉시 생성
@lru_cache()
def get_til_model() -> TILModels:
    """싱글톤 패턴으로 TILModel 인스턴스 제공"""
    return TILModels()