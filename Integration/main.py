from fastapi import FastAPI
from app.api.routes import router
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(debug=True)
app.include_router(router)

Instrumentator().instrument(app).expose(app)

if __name__ == "__main__":
    import uvicorn
    import nest_asyncio
    nest_asyncio.apply()
    uvicorn.run(app, host="0.0.0.0", port=8000)
