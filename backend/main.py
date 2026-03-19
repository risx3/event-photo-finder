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

INDEX_PATH     = Path(__file__).parent / "embeddings_index.pkl"
FRONTEND_DIST  = Path(__file__).parent.parent / "frontend" / "dist"

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))
MAX_RESULTS          = int(os.getenv("MAX_RESULTS", "50"))
MAX_UPLOAD_BYTES     = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024  # default 10 MB
EVENT_NAME           = os.getenv("EVENT_NAME", "My Event")
EVENT_SUBTITLE       = os.getenv("EVENT_SUBTITLE", "Find all your photos from this event")

# Bounded thread pool for CPU-bound face inference.
# Keeps concurrent inference jobs ≤ CPU count so they don't thrash.
_cpu_count      = os.cpu_count() or 2
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
            "total_photos":      data.get("total_photos", 0),
            "total_embeddings":  len(entries),
            "indexed_at":        data.get("indexed_at"),
        }
        app.state.vectors  = vectors    # np.ndarray (n, 512), L2-normalised
        app.state.metadata = metadata  # list[dict] — no embedding arrays
        logger.info(
            f"Index loaded: {len(entries)} embeddings from "
            f"{data.get('total_photos', 0)} photos"
        )
    else:
        app.state.index_meta = None
        app.state.vectors    = None
        app.state.metadata   = None
        logger.warning("No index found. Run: uv run python backend/indexer.py")
    yield
    _inference_pool.shutdown(wait=False)


app = FastAPI(title="Event Photo Finder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status")
async def status(request: Request):
    meta = request.app.state.index_meta
    if meta is None:
        return {"indexed": False, "total_photos": 0, "total_embeddings": 0, "indexed_at": None}
    return {"indexed": True, **meta}


@app.get("/api/config")
async def get_config():
    """Return UI configuration values sourced from environment variables."""
    return {
        "event_name":     EVENT_NAME,
        "event_subtitle": EVENT_SUBTITLE,
    }


@app.post("/api/match")
async def match_faces(request: Request, selfie: UploadFile = File(...)):
    logger.info(f"Received selfie: {selfie.filename} ({selfie.content_type})")

    if selfie.content_type and not selfie.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image")

    image_bytes = await selfie.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    # Run CPU-bound inference off the event loop so other requests aren't blocked.
    loop = asyncio.get_running_loop()
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

    vectors  = request.app.state.vectors
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


# ── Frontend SPA ──────────────────────────────────────────────────────────────
# Must be registered AFTER all /api/* routes so API routes take priority.

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """
    Serve the built React app from frontend/dist/.

    - Exact static file matches (JS, CSS, images) are served directly.
    - Every other path returns index.html so React handles client navigation.

    Development workflow:
        cd frontend && npm run dev   (Vite on :5173, proxies /api → :8000)

    Production workflow:
        cd frontend && npm run build  (outputs to frontend/dist/)
        uv run uvicorn backend.main:app
    """
    dist = FRONTEND_DIST

    # Serve exact static files, with a path-traversal guard
    if full_path:
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
            if candidate.is_file():
                return FileResponse(str(candidate))
        except ValueError:
            pass  # traversal attempt — fall through to index.html

    # SPA entry point (also handles "/")
    html = dist / "index.html"
    if html.exists():
        return FileResponse(str(html), media_type="text/html")

    from fastapi.responses import JSONResponse
    return JSONResponse(
        {"detail": "Frontend not built. Run: cd frontend && npm run build"},
        status_code=503,
    )
