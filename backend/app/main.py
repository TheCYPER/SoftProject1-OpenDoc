from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai_jobs, documents, health, shares, users, versions
from app.database import init_db
from app.realtime import websocket as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Collaborative Document Editor API",
        version="0.1.0",
        description="Real-time collaborative document editing with AI writing assistant",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routers
    app.include_router(health.router)
    app.include_router(users.router)
    app.include_router(documents.router)
    app.include_router(versions.router)
    app.include_router(shares.router)
    app.include_router(ai_jobs.router)

    # WebSocket
    app.include_router(ws_router.router)

    return app


app = create_app()
