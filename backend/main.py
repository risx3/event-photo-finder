import os
import sys
import pickle
import logging
import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from face_engine import get_best_embedding, build_search_index, search_index

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

INDEX_PATH = Path(__file__).parent / "embeddings_index.pkl"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend" / "index.html"

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "50"))

# Bounded thread pool for CPU-bound face inference.
# Keeps concurrent inference jobs ≤ CPU count so they don't thrash.
_cpu_count = os.cpu_count() or 2
_inference_pool = concurrent.futures.ThreadPoolExecutor(max_workers=_cpu_count)


def _load_index_from_disk() -> dict | None:
    if not INDEX_PATH.exists():
        return None
    with open(INDEX_PATH, "rb") as f:
        return pickle.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embeddings index once at startup and keep it in memory."""
    data = _load_index_from_disk()
    if data:
        entries = data.get("entries", [])
        # Pre-build the vectorized search index (normalised numpy matrix + metadata list).
        vectors, metadata = build_search_index(entries)
        app.state.index_meta = {
            "total_photos": data.get("total_photos", 0),
            "total_embeddings": len(entries),
            "indexed_at": data.get("indexed_at"),
        }
        app.state.vectors = vectors    # np.ndarray (n, 512), L2-normalised
        app.state.metadata = metadata  # list[dict] — no embedding arrays
        logger.info(
            f"Index loaded: {len(entries)} embeddings from "
            f"{data.get('total_photos', 0)} photos"
        )
    else:
        app.state.index_meta = None
        app.state.vectors = None
        app.state.metadata = None
        logger.warning("No index found. Run: uv run python backend/indexer.py")
    yield
    _inference_pool.shutdown(wait=False)


app = FastAPI(title="Wedding Photo Finder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    if not FRONTEND_PATH.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(str(FRONTEND_PATH), media_type="text/html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status")
async def status(request: Request):
    meta = request.app.state.index_meta
    if meta is None:
        return {"indexed": False, "total_photos": 0, "total_embeddings": 0, "indexed_at": None}
    return {"indexed": True, **meta}


@app.post("/api/match")
async def match_faces(request: Request, selfie: UploadFile = File(...)):
    logger.info(f"Received selfie: {selfie.filename} ({selfie.content_type})")

    if selfie.content_type and not selfie.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image")

    image_bytes = await selfie.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Run CPU-bound inference off the event loop so other requests aren't blocked.
    loop = asyncio.get_event_loop()
    try:
        embedding = await loop.run_in_executor(
            _inference_pool, get_best_embedding, image_bytes
        )
    except Exception as e:
        logger.error(f"Face extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Face processing error: {str(e)}")

    if embedding is None:
        logger.info("No face detected in uploaded selfie")
        return {
            "success": False,
            "error": "No face detected in selfie, please try again",
            "matched_count": 0,
            "photos": [],
        }

    vectors = request.app.state.vectors
    metadata = request.app.state.metadata

    if vectors is None:
        raise HTTPException(
            status_code=503,
            detail="Photo index not built yet. Run: uv run python backend/indexer.py",
        )

    if len(metadata) == 0:
        return {"success": True, "matched_count": 0, "photos": []}

    matches = search_index(embedding, vectors, metadata, SIMILARITY_THRESHOLD, MAX_RESULTS)
    logger.info(f"Found {len(matches)} matching photo(s) above threshold {SIMILARITY_THRESHOLD}")

    return {"success": True, "matched_count": len(matches), "photos": matches}
