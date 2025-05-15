import os
from qdrant_client import QdrantClient
from vllm import AsyncEngineArgs, AsyncLLMEngine
from dotenv import load_dotenv

load_dotenv()

base_llm = os.getenv("MODEL_PATH")

engine_args = AsyncEngineArgs(
    model=base_llm,
    tensor_parallel_size=1, # GPU 개수
    gpu_memory_utilization=0.95,
    max_num_seqs = 100, # 동시에 받을 수 있는 요청 개수
    max_model_len=4096, # input + output 토큰 길이
    max_num_batched_tokens=8192) # 한 batch 당 토근 길이 

llm = AsyncLLMEngine.from_engine_args(engine_args)

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST"), 
    port=os.getenv("QDRANT_PORT"))
