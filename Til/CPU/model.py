from llama_cpp import Llama
from dotenv import load_dotenv
import os

load_dotenv()

MISTRAL_7B_Q4KM_PATH = os.getenv("MISTRAL_7B_Q4KM_PATH")
HYPERCLOVAX_SEED_Q4KM_PATH = os.getenv("HYPERCLOVAX_SEED_Q4KM_PATH")

class LLM:
    def __init__(self):
        self.model = Llama(
            model_path = MISTRAL_7B_Q4KM_PATH,
            n_gpu_layers=40,
            n_batch=128,
            n_ctx=4096
        )

        self.translator = Llama(
            model_path= HYPERCLOVAX_SEED_Q4KM_PATH,
            n_gpu_layers=25,
            n_batch=128,
            n_ctx=2048
        )

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2024,
        temperature: float = 0.3,
        top_p: float = 0.95,
        frequency_penalty: float = 0.3,
        repeat_penalty: float = 1.1,
        stop: list[str] = None,
    ) -> str:

        response = self.model.create_chat_completion(
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            repeat_penalty=repeat_penalty,
            stop=stop or [],  # 기본값으로 빈 리스트
        )

        return response["choices"][0]["message"]["content"].strip()
    
    async def translate(
        self,
        prompt: str,
        max_tokens: int = 3000,
        temperature: float = 0.3,
        top_p: float = 0.95,
        frequency_penalty: float = 0.3,
        repeat_penalty: float = 1.1,
        stop: list[str] = None,
    ) -> str:

        response = self.translator.create_chat_completion(
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            repeat_penalty=repeat_penalty,
            stop=stop or [],  # 기본값으로 빈 리스트
        )

        return response["choices"][0]["message"]["content"].strip()