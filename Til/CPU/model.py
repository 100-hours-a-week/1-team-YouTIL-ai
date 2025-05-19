# model.py
import os
from llama_cpp import Llama

NUM_CPU_THREADS = os.cpu_count()

class LLM:
    def __init__(self):
        self.model = Llama(
            model_path="/home/a01088415234/models/gemma-3-4b-it-gguf/gemma-3-4b-it-Q4_K_M.gguf",
            n_gpu_layers=-1,
            n_threads=NUM_CPU_THREADS,
            n_batch=128,
            n_ctx=4096
        )

    async def generate(self, prompt: str, max_tokens: int) -> str:
        response = self.model(
            prompt,
            max_tokens=max_tokens,
            stop=["<eos>", "</s>", "---", "```", "<|endoftext|>"],
            temperature=0.7,
            top_p=0.9
        )
        return response["choices"][0]["text"].strip()
