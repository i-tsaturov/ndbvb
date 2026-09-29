from fastapi import APIRouter

router = APIRouter(tags=["core"])


@router.get("/api/v1/core/health", summary="Service health")
def health():
    return {"status": "ok", "service": "onlinebank-api"}
