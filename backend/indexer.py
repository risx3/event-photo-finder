"""
Wedding Photo Indexer
---------------------
Run this script once (and re-run after adding new photos) to build
the face embeddings index from all photos stored in Google Drive.

Usage:
    uv run python backend/indexer.py
"""

import os
import sys
import pickle
import logging
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from tqdm import tqdm
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TEMP_DIR = Path(__file__).parent.parent / "temp"
INDEX_PATH = Path(__file__).parent / "embeddings_index.pkl"

# Number of parallel Drive downloads. Drive API handles this well;
# increase if your network allows it.
DOWNLOAD_WORKERS = 10


def _download_one(args: tuple) -> tuple[dict, Path, bool]:
    """Download a single file. Returns (file_info, dest_path, success)."""
    client, file_info = args
    file_id = file_info["id"]
    # Prefix with file_id to avoid name collisions in the temp folder.
    dest = TEMP_DIR / f"{file_id}_{file_info['name']}"
    success = client.download_file(file_id, str(dest))
    return file_info, dest, success


def run_indexer():
    from drive_client import DriveClient
    from face_engine import get_all_embeddings

    TEMP_DIR.mkdir(exist_ok=True)

    logger.info("Connecting to Google Drive...")
    client = DriveClient()

    logger.info("Listing images in Drive folder...")
    files = client.list_images()
    logger.info(f"Found {len(files)} image(s) to process.")

    if not files:
        logger.warning("No images found. Check your GOOGLE_DRIVE_FOLDER_ID and folder sharing.")
        return

    index: list[dict] = []
    total_faces = 0
    skipped = 0
    index_lock = Lock()  # guard shared state across threads if needed

    # ── Phase 1: parallel downloads ───────────────────────────────────────
    # Downloads are network-IO-bound, so parallelising gives a large speedup.
    # Face extraction (CPU-bound) happens in the main thread after each download
    # completes, keeping CPU usage predictable.
    logger.info(f"Starting parallel downloads with {DOWNLOAD_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        futures = {
            executor.submit(_download_one, (client, f)): f for f in files
        }

        with tqdm(total=len(files), desc="Indexing photos", unit="photo") as pbar:
            for future in as_completed(futures):
                file_info, dest, success = future.result()
                file_id = file_info["id"]
                filename = file_info["name"]

                try:
                    if not success:
                        logger.warning(f"Skipped (download failed): {filename}")
                        skipped += 1
                        continue

                    # ── Phase 2: face extraction (CPU, main thread) ───────
                    embeddings = get_all_embeddings(str(dest))

                    if not embeddings:
                        logger.debug(f"No faces detected: {filename}")
                        skipped += 1
                        continue

                    for emb in embeddings:
                        index.append(
                            {
                                "embedding": emb,
                                "file_id": file_id,
                                "filename": filename,
                                "view_url": client.get_view_url(file_id),
                                "download_url": client.get_download_url(file_id),
                                "thumbnail_url": client.get_thumbnail_url(file_id),
                            }
                        )
                    total_faces += len(embeddings)

                except Exception as e:
                    logger.error(f"Error processing {filename}: {e}")
                    skipped += 1
                finally:
                    dest.unlink(missing_ok=True)
                    pbar.update(1)

    # ── Save index ────────────────────────────────────────────────────────
    payload = {
        "entries": index,
        "total_photos": len(files) - skipped,
        "total_faces": total_faces,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(INDEX_PATH, "wb") as f:
        pickle.dump(payload, f)

    logger.info("")
    logger.info("=" * 50)
    logger.info("Indexing complete!")
    logger.info(f"  Photos processed : {len(files) - skipped}")
    logger.info(f"  Faces detected   : {total_faces}")
    logger.info(f"  Skipped photos   : {skipped}")
    logger.info(f"  Index saved to   : {INDEX_PATH}")
    logger.info("=" * 50)

    # Clean up any leftover temp files
    for f in TEMP_DIR.iterdir():
        if f.name != ".gitkeep":
            f.unlink(missing_ok=True)
    logger.info("Temp folder cleaned up.")


if __name__ == "__main__":
    run_indexer()
