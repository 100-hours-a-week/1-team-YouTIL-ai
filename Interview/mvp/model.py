import os
import logging
from qdrant_client import QdrantClient
from vllm import AsyncEngineArgs, AsyncLLMEngine
from dotenv import load_dotenv

load_dotenv()

base_llm = os.getenv("MODEL2_PATH")

engine_args = AsyncEngineArgs(
    model=base_llm,
    tensor_parallel_size=1, 
    gpu_memory_utilization=0.95,
    max_num_seqs = 32, 
    max_model_len=4096,
    max_num_batched_tokens=4096)

llm = AsyncLLMEngine.from_engine_args(engine_args)

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST"), 
    port=os.getenv("QDRANT_PORT"))
