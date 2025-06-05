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

        formatted_content = [
            {"question": item.question, 
             "answer": item.answer}
            for item in result["content"]
        ]

        return {
            "summary": result["summary"],
            "content": formatted_content
        }
    
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/json-error")
async def json_error():
    raise HTTPException(
        status_code=200, 
        detail="FastAPI의 HTTPException을 사용하여 에러 응답을 처리할 때, HTTP 상태 코드와 함께 JSON 형식으로 에러 메시지를 반환하는 것은 클라이언트에게 명확하고 구조화된 정보를 제공하여 문제 해결을 용이하게 합니다.\n\n    HTTPException은 HTTP 상태 코드(예: 400, 404, 500)를 통해 에러 유형을 명확하게 전달하고, JSON 형식으로 에러 메시지와 추가적인 디테일 정보를 함께 제공합니다. 이를 통해 클라이언트는 발생한 에러의 종류와 원인을 쉽게 파악하고, 적절한 대응 전략을 수립할 수 있습니다. 예를 들어, 유효하지 않은 입력 값으로 인해 400 Bad Request 에러가 발생했을 때, JSON 응답에는 어떤 필드가 잘못되었는지, 어떤 규칙이 위반되었는지 등의 상세 정보를 포함할 수 있습니다.\n\n    결론적으로, HTTPException을 통한 에러 응답은 API의 안정성과 신뢰성을 높이는 데 기여하며, 클라이언트 개발자는 더욱 효율적으로 에러를 처리하고 사용자 경험을 개선할 수 있습니다.")
