from Prompts import *
from state_types import StateModel
from Langgraph_nodes import Langgraph
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from discord_client import DiscordClient
from prometheus_fastapi_instrumentator import Instrumentator
from model import *
from dotenv import load_dotenv
import uvicorn
import asyncio
import nest_asyncio
from llama_cpp import Llama

import os
import httpx

# 디버깅 패키지
import traceback

load_dotenv()
app = FastAPI(debug=True)
# 프로메테우스 연동
Instrumentator().instrument(app).expose(app)

NUM_CPU_THREADS = os.cpu_count() 

class LLM:
    def __init__(self):
        self.model = Llama(
            model_path="/home/a01088415234/models/gemma-3-4b-it-gguf/gemma-3-4b-it-Q4_K_M.gguf",
            n_gpu_layers=-1,           # GPU 전체 사용
            n_threads=NUM_CPU_THREADS, # CPU 병렬 처리
            n_batch=128,               # 배치 크기
            n_ctx=4096                 # 컨텍스트 길이
        )

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        """LLM 모델로부터 응답 생성"""
        response = self.model(
            prompt,
            max_tokens=max_tokens,
            stop=["<eos>", "</s>", "###"],
            temperature=0.7,
            top_p=0.9
        )
        return response["choices"][0]["text"].strip()

@app.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/til")
async def process_til(data: StateModel):
    try:
        files_num = len(data.files)
        # Langgraph 초기화
        graph = Langgraph(files_num = files_num)
        
        # Langgraph 실행
        result = await graph.graph.ainvoke(data)

        # vector만 제외하고 dict로 반환
        til_json = result["til_json"]
        til_json_dict = til_json.dict(exclude={"vector"})

        
        return til_json_dict
        
    except Exception as e:
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)