from Prompts import *
from state_types import StateModel
from Langgraph_nodes import Langgraph
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from model import LLM
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
# Instrumentator().instrument(app).expose(app)

model = LLM()

@app.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/til")
async def process_til(data: StateModel):
    try:
        files_num = len(data.files)
        # Langgraph 초기화
        graph = Langgraph(files_num, model)
        
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