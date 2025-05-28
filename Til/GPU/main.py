from Prompts import *
from state_types import *
from Langgraph_nodes import *
from evaluation.evaluate import TilEvaluator
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from discord_client import DiscordClient
from prometheus_fastapi_instrumentator import Instrumentator
from model import *
from dotenv import load_dotenv
import uvicorn
import asyncio
import nest_asyncio
import os
import pymysql
import httpx

# 디버깅 패키지
import traceback

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

load_dotenv()

connection_info = {
  "host": os.getenv("DB_SERVER_IP"),
  "user": "til_user",
  "password": os.getenv("MYSQL_DB_PW"),
  "database": "til_db"
}

async def evaluate_and_save_mysql(content, metadata, conn_info):
    try:
        evaluator = TilEvaluator(open_api_key=os.getenv("OPENAI_API_KEY"), content=content)
        response = evaluator.evaluate_til(content)
        parsed = evaluator._parsed_evaluation(response)
        if parsed:
            TilEvaluator.insert_til_evaluation_to_db(parsed, metadata, conn_info)
        else:
            print("❌ 평가 결과를 파싱할 수 없어 DB 저장 생략")
    except Exception as e:
        # 로그로만 남기고 종료 (예외를 throw하지 않음)
        print(f"[TIL 평가 실패] {e}")

app = FastAPI(debug=True)
# 프로메테우스 연동
Instrumentator().instrument(app).expose(app)

discord_client = DiscordClient()
asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

model = get_til_model()

@app.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})

@app.post("/til")
async def process_til(data: StateModel, background_tasks: BackgroundTasks):
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

        # MySQL에 저장할 metadata
        metadata = {
            "username": til_json_dict["username"],
            "commit_date": til_json_dict["date"],
            "repo": til_json_dict["repo"],
            "content": til_json_dict["content"]
        }

        background_tasks.add_task(evaluate_and_save_mysql, til_json_dict["content"], metadata, connection_info)
        
        return til_json_dict
        
    except Exception as e:
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)