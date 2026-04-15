from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/api/health",
    summary="Liveness check — always returns 200",
)
async def health_check():
    """Used by compose/k8s health probes. No auth required."""
    return {"status": "ok"}
