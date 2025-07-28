import os
import traceback
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

#========================================TIL========================================#
from app.evaluation.til_evaluation.evaluate import TilEvaluator
from app.utils.discord_client import DiscordClient
from app.models.embedding import EmbeddingModel

from app.Til_agent.utils import kafka_produce
from app.Til_agent.agent_schema import InputSchema, CommitDataSchema
from app.Til_agent.supervisor import SupervisorGraph
from app.Til_agent.commit_analysis_tools import CommitTools

import uuid
from langfuse.langchain import CallbackHandler
from langfuse import get_client
from Crypto.Cipher import AES
import base64

#========================================Safety Filter========================================#
from app.safety_filter.filter import SafeFilter
from app.safety_filter.filter import ContentSchema

#=====================================Interview=====================================#
from app.prompts.Interview_Prompts import PromptTemplates
from app.nodes.interview_langgraph_nodes import QAFlow
from app.schemas.Interview_Schema import QAState
from app.evaluation.interview_evaluation.scoring import compute_scores
from app.evaluation.interview_evaluation.store import store_to_db
from app.models.interview_model import model
from app.utils.discord_interview_client import DiscordClientInterview

qa_flow = QAFlow(llm=model.llm, qdrant=model.qdrant, templates=PromptTemplates)
graph = qa_flow.build_graph()
load_dotenv()

os.environ["OTEL_EXPORTER_OTLP_TIMEOUT"] = "600" 

logger = logging.getLogger(__name__)
router = APIRouter()
embedding_model = EmbeddingModel()
discord_client = DiscordClient()
discord_client_interview = DiscordClientInterview()

safe_filter = SafeFilter()

get_commit_data = CommitTools.get_commit_data

# 비동기 Discord 클라이언트 실행
asyncio.create_task(discord_client.start(os.getenv("DISCORD_BOT_TOKEN")))

def unpad(s: bytes) -> bytes:
    return s[:-s[-1]]

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

@router.post("/filter")
async def safety_filter(state: ContentSchema):
    response = await safe_filter.content_filter(state)

    result = {"result": response.filter_type}
    return result

@router.post("/til")
async def commit_analysis(state: InputSchema):
    username = state.owner
    date = state.date
    repo = state.repo
    github_token = state.githubToken


    key = os.getenv("GITHUB_PASSWORD_KEY").encode()
    encrypted_b64 = github_token
    cipher_bytes = base64.b64decode(encrypted_b64)

    cipher = AES.new(key, AES.MODE_ECB)
    decrypted_bytes = cipher.decrypt(cipher_bytes)

    try:
        decrypted = unpad(decrypted_bytes).decode('utf-8')
    except Exception as e:
        print("❌ 복호화 실패:", e)

    try:
        commit_data = await get_commit_data(
            owner=state.owner, 
            repo=state.repo, 
            branch=state.branch, 
            sha_list=state.sha_list,
            github_token=decrypted
        )
        
        if state.requestId is not None:
            kafka_produce(
                requestid=state.requestId, 
                process="GET_COMMIT_DATA_FROM_GITHUB"
            )
        
        input_commit = CommitDataSchema(**commit_data)
        no_files = len(input_commit.files)

        if state.requestId is not None:
            kafka_produce(
                requestid=state.requestId, 
                process="COMMIT_ANALYSIS_START"
            )
        
        graph = await SupervisorGraph(no_files=no_files).make_supervisor_graph()
        input_commit.requestId = state.requestId


        session_id = str(uuid.uuid4())
        langfuse = get_client()
        callback_handler = CallbackHandler()
        
        with langfuse.start_as_current_span(name="dynamic-langchain-trace") as span:
            span.update_trace(
                user_id=state.owner,
                session_id=session_id,
                input=input_commit
            )

            final_result = await graph.ainvoke(input_commit, config={"callbacks": [callback_handler]})
            # span.update_trace(output={"response": final_result})

        selected_output = {
            "username": username,
            "repo": repo,
            "date": date,
            "content": final_result["final_report"],
            # 검색 결과 출력 필요 시 주석 해제
            # "source_str": final_result["source_str"],
            "keywords": final_result["keywords"][:3],
        }

        # 디스코드 팀 채널에 til 결과 전달
        await discord_client.send_til_to_thread(
            content=selected_output["content"],
            username=selected_output["username"]
        )

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

    return {
        "content":selected_output["content"],
        "keywords":selected_output["keywords"]
    }

#========================================Interview========================================#

asyncio.create_task(discord_client_interview.start(os.getenv("DISCORD_TOKEN")))

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

        await discord_client_interview.send_interview_to_channel(
            email=data.email,
            summary=result["summary"],
            content=formatted_content, 
        )

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