from Prompts import *
from state_types import *
from Langgraph_nodes import *
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from model import *
from dotenv import load_dotenv
import uvicorn
import nest_asyncio

# 디버깅 패키지
import traceback

load_dotenv()
app = FastAPI(debug=True)
# 프로메테우스 연동
Instrumentator().instrument(app).expose(app)


# graph = Langgraph(model=model) 

@app.post("/til")
async def process_til(data: StateModel):
    try:
        model = get_til_model()
        # Langgraph 초기화
        graph = Langgraph(model = model)
        
        # # 상태 초기화
        # state = {
        #     "username": data.username,
        #     "date": data.date,
        #     "repo": data.repo,
        #     "files": [
        #         {
        #             "filepath": file.filepath,
        #             "latest_code": file.latest_code,
        #             "patches":  [
        #             {
        #                 "commit_message": patch.commit_message,
        #                 "patch": patch.patch
        #             }
        #             for patch in file.patches
        #         ]
        #         }
        #         for file in data.files
        #     ]
        # }
        
        # Langgraph 실행
        result = await graph.graph.ainvoke(data)
        
        return result["til_json"]
        
    except Exception as e:
        traceback.print_exc()  # <<<<< 핵심
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)

