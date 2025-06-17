import os
import traceback
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

#========================================TIL========================================#
from app.schemas.Til_Schema import StateModel
from app.models import get_til_model
from app.models import EmbeddingModel
from app.nodes.til_langgraph_nodes import Langgraph
from app.evaluation.til_evaluation.evaluate import TilEvaluator
from app.utils.discord_client import DiscordClient

#=====================================Interview=====================================#
from app.prompts.Interview_Prompts import PromptTemplates
from app.nodes.interview_langgraph_nodes import QAFlow
from app.schemas.Interview_Schema import QAState, ContentState
from app.evaluation.interview_evaluation.scoring import compute_scores
from app.evaluation.interview_evaluation.store import store_to_db
from app.models.interview_model import model

qa_flow = QAFlow(llm=model.llm, qdrant=model.qdrant, templates=PromptTemplates)
graph = qa_flow.build_graph()

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()
model = get_til_model()
embedding_model = EmbeddingModel()
discord_client = DiscordClient()

# 비동기 Discord 클라이언트 실행
asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

# Til 평가 DB 연결 정보
connection_info = {
    "host": os.getenv("DB_SERVER_IP"),
    "user": "til_user",
    "password": os.getenv("MYSQL_DB_PW"),
    "database": "til_db"
}



@router.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})


#========================================TIL========================================#

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
        graph = Langgraph(files_num=files_num, model=model, embedding=embedding_model)
        result = await graph.graph.ainvoke(data)
        til_json = result["til_json"]
        til_json_dict = til_json.dict(exclude={"vector"})

        keywords = til_json_dict["keywords"]["keywords_list"]

        til_json_dict["keywords"] = keywords

        # 디스코드 팀 채널에 til 결과 전달
        await discord_client.send_til_to_thread(
            content=til_json_dict["content"],
            username=til_json_dict["username"]
        )
        # MySQL DB에 전달할 사용자 정보
        metadata = {
            "username": til_json_dict["username"],
            "commit_date": til_json_dict["date"],
            "repo": til_json_dict["repo"],
            "content": til_json_dict["content"]
        }

        # evaluation 과정은 backgroun에서 수행해 til 생성시 클라이언트에게 바로 전달
        background_tasks.add_task(evaluate_and_save_mysql, til_json_dict["content"], metadata, connection_info)
        return til_json_dict

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

#========================================Interview========================================#



#logging.basicConfig(level=logging.DEBUG)

@router.post("/interview")
async def generate(data: QAState):
    try:
        result = await graph.ainvoke(data)

        formatted_content = []

        for idx, item in enumerate(result["content"]):
            question = item.question
            answer = item.answer

            #similarity_score = getattr(data, f"similarity_score{idx}", None)
            similarity_score = result.get(f"similarity_score{idx}", None)
            recall = result.get(f"recall_at_k{idx}", None)

            scores = compute_scores(
                reference=data.til, 
                prediction=answer,
                similarity_score=similarity_score,
                recall_at_k=recall)

            # DB 저장
            store_to_db({
                "til_content": data.til,
                "email": data.email,
                "question": question,
                "answer": answer,
                **scores
            })

            # 클라이언트 응답용 리스트 구성
            formatted_content.append({
                "question": question,
                "answer": answer
            })

        return {
            "summary": result["summary"],
            "content": formatted_content
        }
    
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/json-error")
async def json_error():
    raise HTTPException(
        status_code=200, 
        detail="성공")