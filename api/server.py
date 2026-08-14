"""Unified API Server for Content Machine."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router

app = FastAPI(
    title="Content Machine API",
    description="Unified API for multi-platform content publishing",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
async def root():
    return {
        "name": "Content Machine API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/api")
async def api_info():
    return {
        "version": "1.0.0",
        "endpoints": {
            "tasks": "/api/v1/tasks",
            "platforms": "/api/v1/platforms",
            "health": "/api/v1/health"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=True)