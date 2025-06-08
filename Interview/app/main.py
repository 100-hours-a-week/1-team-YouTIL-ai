from evaluation.scoring import compute_scores
from evaluation.store import store_to_db

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi import HTTPException
import traceback

from model import model
from prompt import PromptTemplates
from graph import QAFlow
from schemas import QAState, ContentState

import requests

qa_flow = QAFlow(llm=model.llm, qdrant=model.qdrant, templates=PromptTemplates)
graph = qa_flow.build_graph()

app = FastAPI(debug=True)

@app.post("/interview")
async def generate(data: QAState):
    try:
        result = await graph.ainvoke(data)

        formatted_content = []

        for idx, item in enumerate(result["content"]):
            question = item.question
            answer = item.answer

            similarity_score = getattr(data, f"similarity_score{idx}", None)

            scores = compute_scores(
                reference=data.til, 
                prediction=answer,
                similarity_score=similarity_score)

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

        # formatted_content = [
        #     {"question": item.question, 
        #      "answer": item.answer}
        #     for item in result["content"]
        # ]

        # return {
        #     "summary": result["summary"],
        #     "content": formatted_content
        # }
    
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/json-error")
async def json_error():
    raise HTTPException(
        status_code=200, 
        detail="성공")