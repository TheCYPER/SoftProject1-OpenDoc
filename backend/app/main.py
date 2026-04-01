from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import ai_jobs, audit, documents, health, shares, users, versions, workspaces
from app.database import init_db
from app.realtime import websocket as ws_router

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def _rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": str(exc.detail)},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Collaborative Document Editor API",
        version="0.1.0",
        description="Real-time collaborative document editing with AI writing assistant",
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]

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
    app.include_router(audit.router)
    app.include_router(workspaces.router)

    # WebSocket
    app.include_router(ws_router.router)

    return app


app = create_app()
