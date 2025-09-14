from fastapi import APIRouter, Request
from services.utils import sh

router = APIRouter()

@router.post("/git/branch")
async def git_branch(req: Request):
    b = await req.json()
    name = b.get("name", "clike/patch")
    out = sh(["git", "checkout", "-b", name])
    return {"ok": True, "output": out}


@router.post("/git/commit")
async def git_commit(req: Request):
    b = await req.json()
    msg = b.get("message", "clike: patch")
    sh(["git", "add", "."])
    out = sh(["git", "commit", "-m", msg])
    return {"ok": True, "output": out}

@router.post("/git/pr")
async def git_pr(req: Request):
    b = await req.json()
    title = b.get("title", "clike: PR")
    try:
        out = sh(["gh", "pr", "create", "--title", title, "--fill"])
        return {"ok": True, "output": out}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

