from state_types import StateModel
from Langgraph_nodes import Langgraph
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from model import LLM
from dotenv import load_dotenv
from discord_client import DiscordClient
import uvicorn
import nest_asyncio
import asyncio

from pyngrok import ngrok

import os

# 디버깅 패키지
import traceback

load_dotenv()
app = FastAPI(debug=True)

discord_client = DiscordClient()

# FastAPI 앱 시작 시 디스코드 봇 실행
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

# TIL 생성, 번역 모델 로딩딩
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
        # til_json_dict = til_json.dict(exclude={"vector"})

        # Discord 스레드 전송 (username, content 전달)        
        await discord_client.send_til_to_thread(
            content=til_json.content,
            username=til_json.username
        )

        
        return til_json
        
    except Exception as e:
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))
    

if __name__ == "__main__":
    # allow nested asyncio loop
    nest_asyncio.apply()

    # ngrok 인증 토큰 설정
    ngrok.set_auth_token(os.getenv("NGROK_AUTH_TOKEN"))

    # uvicorn 서버를 백그라운드로 실행
    public_url = ngrok.connect(8000)
    print("🚀 외부 접속 URL:", public_url)

  

    # 로컬 서버 실행
    uvicorn.run(app, host="0.0.0.0", port=8000)