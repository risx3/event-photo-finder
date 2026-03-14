import os
import sys
import pickle
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, UploadFile, HTTPException
from face_engine import get_best_embedding, find_matches
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Wedding Photo Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_PATH = Path(__file__).parent / "embeddings_index.pkl"
FRONTEND_PATH = Path(__file__).parent.parent / "frontend" / "index.html"

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "50"))


def load_index() -> dict | None:
    if not INDEX_PATH.exists():
        return None
    with open(INDEX_PATH, "rb") as f:
        return pickle.load(f)


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
async def status():
    data = load_index()
    if data is None:
        return {
            "indexed": False,
            "total_photos": 0,
            "total_embeddings": 0,
            "indexed_at": None,
        }
    return {
        "indexed": True,
        "total_photos": data.get("total_photos", 0),
        "total_embeddings": len(data.get("entries", [])),
        "indexed_at": data.get("indexed_at"),
    }


@app.post("/api/match")
async def match_faces(selfie: UploadFile = File(...)):
    logger.info(f"Received selfie: {selfie.filename} ({selfie.content_type})")

    # Validate mime type loosely
    if selfie.content_type and not selfie.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image")

    image_bytes = await selfie.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Extract face embedding
    try:
        embedding = get_best_embedding(image_bytes)
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

    # Load index
    data = load_index()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Photo index not built yet. Run the indexer first: python backend/indexer.py",
        )

    entries = data.get("entries", [])
    if not entries:
        return {"success": True, "matched_count": 0, "photos": []}

    # Match
    matches = find_matches(embedding, entries, SIMILARITY_THRESHOLD, MAX_RESULTS)
    logger.info(f"Found {len(matches)} matching photo(s) above threshold {SIMILARITY_THRESHOLD}")

    photos = [
        {
            "file_id": m["file_id"],
            "filename": m["filename"],
            "view_url": m["view_url"],
            "download_url": m["download_url"],
            "similarity_score": m["similarity_score"],
            "thumbnail_url": m["thumbnail_url"],
        }
        for m in matches
    ]

    return {"success": True, "matched_count": len(photos), "photos": photos}
