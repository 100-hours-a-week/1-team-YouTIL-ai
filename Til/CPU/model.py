# model.py
import os
from llama_cpp import Llama

# NUM_CPU_THREADS = os.cpu_count()

class LLM:
    def __init__(self):
        self.model = Llama(
            model_path = r"C:\Users\mmm06\Desktop\KBT\model\Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
            n_gpu_layers=40,
            # n_threads=NUM_CPU_THREADS,
            n_batch=128,
            n_ctx=4096
        )

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        frequency_penalty: float = 0.0,
        repeat_penalty: float = 1.0,
        stop: list[str] = ["</s>"],
        echo: bool = False,
    ) -> str:
        response = self.model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            repeat_penalty=repeat_penalty,
            stop=stop,
            echo=echo,
        )
        return response["choices"][0]["text"].strip()