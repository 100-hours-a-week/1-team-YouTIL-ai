import uuid
from functools import lru_cache
import logging
from typing import Optional, List

from transformers import AutoTokenizer, AutoModel
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams

logger = logging.getLogger(__name__)

class ModelConfig:
    GEMMA_PATH: str = "/home/mmm060400/KTB/models/google/gemma-3-4b-it/"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    
    # VLLM 설정
    TENSOR_PARALLEL_SIZE: int = 1
    GPU_MEMORY_UTILIZATION: float = 0.95
    MAX_NUM_SEQS: int = 100
    MAX_MODEL_LEN: int = 4096
    MAX_NUM_BATCHED_TOKENS: int = 8192
    
    # 생성 파라미터
    TEMPERATURE: float = 0.6
    TOP_P: float = 0.7
    REPETITION_PENALTY: float = 1.1
    MAX_TOKENS: int = 4096
    STOP_TOKENS: list = ["<eos>"]

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
            
            # 샘플링 파라미터 설정
            self.sampling_params = SamplingParams(
                temperature=self.config.TEMPERATURE,
                top_p=self.config.TOP_P,
                repetition_penalty=self.config.REPETITION_PENALTY,
                max_tokens=self.config.MAX_TOKENS,
                stop=self.config.STOP_TOKENS
            )
            
            logger.info("모델 초기화 완료")
            
        except Exception as e:
            logger.error(f"모델 초기화 실패: {e}")
            raise
    
    async def generate(self, prompt: str) -> str:
        """LLM을 사용하여 텍스트 생성"""
        try:
            request_id = str(uuid.uuid4())
            last_output: Optional[str] = None
            
            async for output in self.llm.generate(
                prompt=prompt,
                sampling_params=self.sampling_params,
                request_id=request_id
            ):
                last_output = output.outputs[0].text
                
            if last_output is None:
                raise ValueError("생성된 출력이 없습니다.")
                
            return last_output
            
        except Exception as e:
            logger.error(f"텍스트 생성 실패: {e}")
            raise
    
    async def generate_til(self, prompt: str) -> str:
        """TIL 생성을 위한 래퍼 메소드"""
        try:
            result = await self.generate(prompt)
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

@lru_cache()
def get_til_model() -> TILModels:
    """싱글톤 패턴으로 TILModel 인스턴스 제공"""
    return TILModels()