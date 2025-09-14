import os, difflib, hashlib, subprocess, re
from typing import List, Optional
from config import settings
RAG_COLL = "clike_rag"
GATEWAY_URL = str(getattr(settings, "GATEWAY_URL", "http://gateway:8000"))
QDRANT_HOST = getattr(settings, "QDRANT_HOST", "qdrant")
QDRANT_PORT = int(getattr(settings, "QDRANT_PORT", 6333))

from pathlib import Path


def write_file(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """
    Scrive il contenuto in un file, creando le cartelle se non esistono.

    Args:
        path: Percorso del file da scrivere.
        content: Testo da scrivere nel file.
        encoding: Codifica del file (default: "utf-8").

    Raises:
        OSError: Se si verifica un errore di I/O durante la scrittura.
    """
    file_path = Path(path)

    # Crea la directory padre se non esiste
    if file_path.parent:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # Scrive il file con l'encoding specificato
    with file_path.open("w", encoding=encoding) as f:
        f.write(content)

def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""

def to_diff(path: str, a: str, b: str) -> str:
    A = a.splitlines(keepends=True)
    B = b.splitlines(keepends=True)
    return "".join(difflib.unified_diff(A, B, fromfile=path, tofile=path, lineterm=""))

def detect_lang(lang: Optional[str], path: str) -> str:
    if lang:
        lang = lang.lower()
    else:
        lang = ""
    if not lang and path:
        if path.endswith(".py"):
            lang = "python"
        elif path.endswith(".go"):
            lang = "go"
        elif path.endswith(".java"):
            lang = "java"
        elif path.endswith(".tsx") or path.endswith(".jsx"):
            lang = "react"
        elif path.endswith(".ts"):
            lang = "typescript"
        elif path.endswith(".js"):
            lang = "javascript"
        else:
            lang = "plaintext"
    if lang == "golang":
        lang = "go"
    if lang == "js":
        lang = "javascript"
    if lang == "ts":
        lang = "typescript"
    if lang == "nodejs":
        lang = "node"
    return lang

# --------------------- RAG utils ---------------------
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams, PointStruct
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore

def maybe_qdrant():
    if QdrantClient:
        try:
            return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        except Exception:
            return None
    return None

def simple_embed(text: str, dims: int = 256) -> List[float]:
    v = [0.0] * dims
    for tok in text.split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dims
        v[h] += 1.0
    import math
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x / n for x in v]

# ---------------------- GIT utils ----------------------
def sh(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return out.decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.output.decode("utf-8", errors="ignore"))
