import os
import traceback
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from app.schemas.state_types import StateModel
from app.models import get_til_model
from app.nodes.Langgraph_nodes import Langgraph
from app.evaluation.evaluate import TilEvaluator
from app.utils.discord_client import DiscordClient

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()
model = get_til_model()
discord_client = DiscordClient()

# 비동기 Discord 클라이언트 실행
asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

# DB 연결 정보
connection_info = {
    "host": os.getenv("DB_SERVER_IP"),
    "user": "til_user",
    "password": os.getenv("MYSQL_DB_PW"),
    "database": "til_db"
}

@router.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})


async def evaluate_and_save_mysql(content, metadata, conn_info):
    try:
        evaluator = TilEvaluator(open_api_key=os.getenv("OPENAI_API_KEY"), content=content)
        response = evaluator.evaluate_til(content)
        parsed = evaluator._parsed_evaluation(response)
        if parsed:
            TilEvaluator.insert_til_evaluation_to_db(parsed, metadata, conn_info)
        else:
            logger.warning("❌ 평가 결과를 파싱할 수 없어 DB 저장 생략")
    except Exception as e:
        logger.error(f"[TIL 평가 실패] {e}")


@router.post("/til", tags=["TIL"])
async def process_til(data: StateModel, background_tasks: BackgroundTasks):
    try:
        files_num = len(data.files)
        graph = Langgraph(files_num=files_num, model=model)
        result = await graph.graph.ainvoke(data)
        til_json = result["til_json"]
        til_json_dict = til_json.dict(exclude={"vector"})

        await discord_client.send_til_to_thread(
            content=til_json_dict["content"],
            username=til_json_dict["username"]
        )

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
