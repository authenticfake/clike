from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"clike gateway status": "ok"}

