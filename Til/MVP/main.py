from Prompts import *
from state_types import *
from Langgraph_nodes import *
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from discord_client import DiscordClient
from prometheus_fastapi_instrumentator import Instrumentator
from model import *
from dotenv import load_dotenv
import uvicorn
import asyncio
import nest_asyncio
import os
import httpx

# 디버깅 패키지
import traceback

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

load_dotenv()
app = FastAPI(debug=True)
# 프로메테우스 연동
Instrumentator().instrument(app).expose(app)

discord_client = DiscordClient()
asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

async def send_discord_notification(content: str):
    if not DISCORD_WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL is not set in .env")

    async with httpx.AsyncClient() as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"content": content})

model = get_til_model()

@app.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/til")
async def process_til(data: StateModel):
    try:
        files_num = len(data.files)
        # Langgraph 초기화
        graph = Langgraph(files_num = files_num, model = model)
        
        # Langgraph 실행
        result = await graph.graph.ainvoke(data)

        # vector만 제외하고 dict로 반환
        til_json = result["til_json"]
        til_json_dict = til_json.dict(exclude={"vector"})

        # Discord 스레드 전송 (username, content 전달)
        await discord_client.send_til_to_thread(
            content=til_json_dict["content"],
            username=til_json_dict["username"]
        )
        
        return til_json_dict
        
    except Exception as e:
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)