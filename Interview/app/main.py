from fastapi import FastAPI
from fastapi.responses import JSONResponse
import traceback

from model import model
from prompt import PromptTemplates
from graph import QAFlow
from schemas import QAState, ContentState

qa_flow = QAFlow(llm=model.llm, qdrant=model.qdrant, templates=PromptTemplates)
graph = qa_flow.build_graph()

app = FastAPI(debug=True)

@app.post("/interview")
async def generate(data: QAState):
    try:
        result = await graph.ainvoke(data)

        formatted_content = [
            {"question": item.question, "answer": item.answer}
            for item in result["content"]
        ]

        return {
            "summary": result["summary"],
            "content": formatted_content
        }
    
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})