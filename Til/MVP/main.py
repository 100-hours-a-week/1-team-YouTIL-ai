from Prompts import *
from state_types import *
from Langgraph_nodes import *
from fastapi import FastAPI, HTTPException
from model import get_til_model
import uvicorn
import nest_asyncio

app = FastAPI()


@app.post("/til")
async def process_til(data: StateType):
    try:
        # TIL 모델 가져오기
        til_model = get_til_model()
        
        # Langgraph 초기화
        graph = Langgraph()
        
        # 상태 초기화
        state = {
            "username": data.username,
            "date": data.date,
            "repo": data.repo,
            "files": [
                {
                    "filepath": file.filepath,
                    "latest_code": file.latest_code,
                    "patches": [
                        {
                            "commit_message": patch["commit_message"],
                            "patch": patch["patch"]
                        }
                        for patch in file.patches
                    ]
                }
                for file in data.files
            ]
        }
        
        # Langgraph 실행
        result = await graph.graph.arun(state)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)

