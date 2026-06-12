"""
Event Photo Indexer
-------------------
Run this script once (and re-run after adding new photos) to build
the face embeddings index from all photos stored in Google Drive.

Usage:
    uv run python backend/indexer.py
"""

import os
import re
import sys
import pickle
import logging
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import (
    ThreadPoolExecutor,
    ProcessPoolExecutor,
    FIRST_COMPLETED,
    TimeoutError as FutureTimeoutError,
    wait,
)
from concurrent.futures.process import BrokenProcessPool

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

# Number of parallel Drive downloads. Each in-flight download holds a
# decoded image in memory, so keep this low on low-RAM hosts (e.g. EC2
# t3.small with 2GB RAM).
DOWNLOAD_WORKERS = 3

# Face extraction runs in a separate worker process. A small minority of
# photos can crash or hang the ONNX/opencv stack outright (segfaults aren't
# catchable in Python) — isolating it in a subprocess means one bad photo
# only costs us that photo, not the whole multi-hour run.
FACE_EXTRACTION_TIMEOUT = 120  # seconds

# Periodically persist progress so a crash/kill doesn't lose hours of work.
CHECKPOINT_EVERY = 100  # photos


def _download_one(args: tuple) -> tuple[dict, Path, bool]:
    """Download a single file. Returns (file_info, dest_path, success)."""
    client, file_info = args
    file_id = file_info["id"]
    # Sanitize filename to strip path separators and unsafe characters.
    safe_name = re.sub(r"[^\w.\-]", "_", file_info["name"])
    # Prefix with file_id to avoid name collisions in the temp folder.
    dest = TEMP_DIR / f"{file_id}_{safe_name}"
    success = client.download_file(file_id, str(dest))
    return file_info, dest, success


def _load_existing_index() -> tuple[list[dict], set[str]]:
    """Load a previously saved index (if any) to resume an interrupted run."""
    if not INDEX_PATH.exists():
        return [], set()
    with open(INDEX_PATH, "rb") as f:
        payload = pickle.load(f)
    entries = payload.get("entries", [])
    processed_ids = {e["file_id"] for e in entries}
    logger.info(
        f"Found existing index with {len(entries)} embeddings from "
        f"{len(processed_ids)} photo(s) — resuming."
    )
    return entries, processed_ids


def run_indexer():
    from drive_client import DriveClient
    from face_engine import get_all_embeddings

    TEMP_DIR.mkdir(exist_ok=True)

    logger.info("Connecting to Google Drive...")
    client = DriveClient()

    logger.info("Listing images in Drive folder...")
    all_files = client.list_images()
    logger.info(f"Found {len(all_files)} image(s) total.")

    if not all_files:
        logger.warning("No images found. Check your GOOGLE_DRIVE_FOLDER_ID and folder sharing.")
        return

    index, processed_ids = _load_existing_index()
    total_faces = sum(1 for _ in index)
    files = [f for f in all_files if f["id"] not in processed_ids]
    skipped = 0

    if not files:
        logger.info("All photos already indexed. Nothing to do.")
        return

    logger.info(f"{len(files)} photo(s) remaining to process.")

    # ── CPU-bound face extraction runs in its own process ──────────────────
    cpu_executor = ProcessPoolExecutor(max_workers=1)

    def _extract_embeddings(dest_path: str):
        """Run face extraction in the worker process, recovering if it
        crashes or hangs by recreating the pool."""
        nonlocal cpu_executor
        try:
            future = cpu_executor.submit(get_all_embeddings, dest_path)
            return future.result(timeout=FACE_EXTRACTION_TIMEOUT)
        except (BrokenProcessPool, FutureTimeoutError) as e:
            logger.error(f"Face extraction worker failed ({e}); restarting worker.")
            cpu_executor.shutdown(wait=False)
            cpu_executor = ProcessPoolExecutor(max_workers=1)
            return None

    processed_since_checkpoint = 0

    def _checkpoint():
        payload = {
            "entries": index,
            "total_photos": len({e["file_id"] for e in index}),
            "total_faces": len(index),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(INDEX_PATH, "wb") as f:
            pickle.dump(payload, f)

    # ── Parallel downloads ───────────────────────────────────────────────
    # Downloads are network-IO-bound, so parallelising gives a large speedup.
    # Face extraction (CPU-bound) happens via cpu_executor after each
    # download completes, keeping CPU usage predictable.
    logger.info(f"Starting parallel downloads with {DOWNLOAD_WORKERS} workers...")

    try:
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
            # Bound the number of in-flight + downloaded-but-unprocessed files.
            # Face extraction is slower than the download workers, so without
            # this limit, downloaded files pile up in TEMP_DIR until disk
            # space runs out.
            MAX_PENDING = DOWNLOAD_WORKERS * 2

            files_iter = iter(files)
            pending = {}

            def _submit_next():
                f = next(files_iter, None)
                if f is not None:
                    pending[executor.submit(_download_one, (client, f))] = f

            for _ in range(MAX_PENDING):
                _submit_next()

            with tqdm(total=len(files), desc="Indexing photos", unit="photo") as pbar:
                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        del pending[future]
                        file_info, dest, success = future.result()
                        file_id = file_info["id"]
                        filename = file_info["name"]

                        try:
                            if not success:
                                logger.warning(f"Skipped (download failed): {filename}")
                                skipped += 1
                                continue

                            # ── Face extraction (isolated worker process) ──
                            embeddings = _extract_embeddings(str(dest))

                            if embeddings is None:
                                logger.warning(f"Skipped (extraction failed): {filename}")
                                skipped += 1
                                continue

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
                            _submit_next()

                            processed_since_checkpoint += 1
                            if processed_since_checkpoint >= CHECKPOINT_EVERY:
                                _checkpoint()
                                processed_since_checkpoint = 0
    except KeyboardInterrupt:
        logger.warning("Indexing interrupted — saving progress and cleaning up temp files...")
        _checkpoint()
        for f in TEMP_DIR.iterdir():
            if f.name != ".gitkeep":
                f.unlink(missing_ok=True)
        logger.info("Progress saved. Re-run to resume. Exiting.")
        return
    finally:
        cpu_executor.shutdown(wait=False)

    # ── Save index ────────────────────────────────────────────────────────
    _checkpoint()

    total_photos = len({e["file_id"] for e in index})
    logger.info("")
    logger.info("=" * 50)
    logger.info("Indexing complete!")
    logger.info(f"  Photos with faces : {total_photos}")
    logger.info(f"  Faces detected    : {total_faces}")
    logger.info(f"  Skipped photos    : {skipped}")
    logger.info(f"  Index saved to    : {INDEX_PATH}")
    logger.info("=" * 50)

    # Clean up any leftover temp files
    for f in TEMP_DIR.iterdir():
        if f.name != ".gitkeep":
            f.unlink(missing_ok=True)
    logger.info("Temp folder cleaned up.")


if __name__ == "__main__":
    run_indexer()
