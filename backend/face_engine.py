import logging
import numpy as np
import cv2
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

_app: FaceAnalysis | None = None


def get_face_app() -> FaceAnalysis:
    """Lazy-load and return the InsightFace app (buffalo_l model)."""
    global _app
    if _app is None:
        logger.info("Loading InsightFace buffalo_l model (downloads on first run)...")
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace model loaded.")
    return _app


def load_image(path_or_bytes: str | bytes) -> np.ndarray:
    """Load image from file path or raw bytes into a BGR numpy array."""
    if isinstance(path_or_bytes, str):
        img = cv2.imread(path_or_bytes)
    else:
        arr = np.frombuffer(path_or_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    return img


def get_all_embeddings(image_path: str) -> list[np.ndarray]:
    """Detect all faces in an image and return their embeddings."""
    app = get_face_app()
    img = load_image(image_path)
    faces = app.get(img)
    return [face.embedding for face in faces] if faces else []


def get_best_embedding(image_bytes: bytes) -> np.ndarray | None:
    """
    Extract the best (largest/most-centered) face embedding from selfie bytes.
    Returns None if no face is detected.
    """
    app = get_face_app()
    img = load_image(image_bytes)
    faces = app.get(img)
    if not faces:
        return None
    if len(faces) == 1:
        return faces[0].embedding

    h, w = img.shape[:2]
    cx, cy = w / 2, h / 2

    def face_score(face) -> float:
        bbox = face.bbox
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        face_cx = (bbox[0] + bbox[2]) / 2
        face_cy = (bbox[1] + bbox[3]) / 2
        dist = ((face_cx - cx) ** 2 + (face_cy - cy) ** 2) ** 0.5
        return area - dist * 0.5

    return max(faces, key=face_score).embedding


def build_search_index(
    entries: list[dict],
) -> tuple[np.ndarray, list[dict]]:
    """
    Pre-process the raw entries list into a fast search structure.

    Returns:
        vectors  — float32 matrix (n, 512), each row L2-normalised
        metadata — parallel list of dicts with all keys except 'embedding'

    Call this once at server startup and cache the results.
    """
    if not entries:
        return np.empty((0, 512), dtype=np.float32), []

    vectors = np.array([e["embedding"] for e in entries], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors /= norms

    metadata = [{k: v for k, v in e.items() if k != "embedding"} for e in entries]
    return vectors, metadata


def search_index(
    query_embedding: np.ndarray,
    vectors: np.ndarray,
    metadata: list[dict],
    threshold: float,
    max_results: int,
) -> list[dict]:
    """
    Vectorised cosine-similarity search.

    Normalise the query once, then compute all similarities with a single
    matrix multiply — O(n) in C rather than a Python loop.
    """
    q = query_embedding.astype(np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return []
    q /= q_norm

    # scores shape: (n,)
    scores = vectors @ q

    # Keep only scores above threshold
    above = np.where(scores >= threshold)[0]
    if above.size == 0:
        return []

    # Deduplicate by file_id, keeping highest score per photo
    seen: dict[str, dict] = {}
    for idx in above:
        score = float(scores[idx])
        entry = metadata[idx]
        fid = entry["file_id"]
        if fid not in seen or score > seen[fid]["similarity_score"]:
            seen[fid] = {**entry, "similarity_score": round(score, 4)}

    results = sorted(seen.values(), key=lambda x: x["similarity_score"], reverse=True)
    return results[:max_results]
