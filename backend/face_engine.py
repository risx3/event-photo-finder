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
    if isinstance(path_or_bytes, (str, bytes)) and not isinstance(
        path_or_bytes, bytes
    ):
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
    if not faces:
        return []
    return [face.embedding for face in faces]


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
        bbox = face.bbox  # [x1, y1, x2, y2]
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        face_cx = (bbox[0] + bbox[2]) / 2
        face_cy = (bbox[1] + bbox[3]) / 2
        dist = ((face_cx - cx) ** 2 + (face_cy - cy) ** 2) ** 0.5
        # prefer large and centered faces
        return area - dist * 0.5

    best = max(faces, key=face_score)
    return best.embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))


def find_matches(
    query_embedding: np.ndarray,
    index: list[dict],
    threshold: float,
    max_results: int,
) -> list[dict]:
    """
    Compare query_embedding against all entries in index.

    Each index entry is expected to have an 'embedding' key.
    Returns a list of matches (sorted by similarity desc) with similarity_score injected.
    """
    scored = []
    for entry in index:
        score = cosine_similarity(query_embedding, entry["embedding"])
        if score >= threshold:
            scored.append({**entry, "similarity_score": round(score, 4)})

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)

    # Deduplicate by file_id, keeping highest score per photo
    seen: dict[str, dict] = {}
    for match in scored:
        fid = match["file_id"]
        if fid not in seen or match["similarity_score"] > seen[fid]["similarity_score"]:
            seen[fid] = match

    results = sorted(seen.values(), key=lambda x: x["similarity_score"], reverse=True)
    return results[:max_results]
