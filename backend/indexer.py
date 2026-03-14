"""
Wedding Photo Indexer
---------------------
Run this script once (and re-run after adding new photos) to build
the face embeddings index from all photos stored in Google Drive.

Usage:
    python backend/indexer.py
"""

import os
import sys
import pickle
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm
from dotenv import load_dotenv

# Allow running from project root or backend/
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

    for file_info in tqdm(files, desc="Indexing photos", unit="photo"):
        file_id = file_info["id"]
        filename = file_info["name"]
        dest = TEMP_DIR / filename

        try:
            success = client.download_file(file_id, str(dest))
            if not success:
                logger.warning(f"  Skipped (download failed): {filename}")
                skipped += 1
                continue

            embeddings = get_all_embeddings(str(dest))

            if not embeddings:
                logger.debug(f"  No faces detected: {filename}")
                skipped += 1
                dest.unlink(missing_ok=True)
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
            logger.error(f"  Error processing {filename}: {e}")
            skipped += 1
        finally:
            dest.unlink(missing_ok=True)

    # Save index
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
    logger.info(f"Indexing complete!")
    logger.info(f"  Photos processed : {len(files) - skipped}")
    logger.info(f"  Faces detected   : {total_faces}")
    logger.info(f"  Skipped photos   : {skipped}")
    logger.info(f"  Index saved to   : {INDEX_PATH}")
    logger.info("=" * 50)

    # Clean up temp dir
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(exist_ok=True)
        logger.info("Temp folder cleaned up.")


if __name__ == "__main__":
    run_indexer()
