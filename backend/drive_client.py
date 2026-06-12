import os
import io
import logging
import threading
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
}


class DriveClient:
    def __init__(self):
        sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_path:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env")
        if not Path(sa_path).exists():
            raise FileNotFoundError(f"Service account JSON not found at: {sa_path}")

        self._sa_path = sa_path
        self._credentials = service_account.Credentials.from_service_account_file(
            sa_path, scopes=SCOPES
        )
        self._local = threading.local()
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not self.folder_id:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID is not set in .env")

    @property
    def service(self):
        """A Drive API service instance, one per thread.

        The underlying httplib2 HTTP connection is not thread-safe, so
        sharing a single `service` object across ThreadPoolExecutor workers
        can corrupt concurrent downloads (SSL errors, garbled responses).
        """
        if not hasattr(self._local, "service"):
            self._local.service = build("drive", "v3", credentials=self._credentials)
        return self._local.service

    def _list_children(self, folder_id: str, query_extra: str) -> list[dict]:
        """List all children of a folder matching an additional query clause."""
        files = []
        page_token = None

        query = f"'{folder_id}' in parents and trashed = false and ({query_extra})"

        while True:
            params = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token

            response = self.service.files().list(**params).execute()
            files.extend(response.get("files", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files

    def list_images(self) -> list[dict]:
        """List all image files in the configured Drive folder, recursing into sub-folders."""
        image_query = " or ".join(f"mimeType = '{m}'" for m in IMAGE_MIME_TYPES)
        folder_query = "mimeType = 'application/vnd.google-apps.folder'"

        files = []
        folders_to_visit = [self.folder_id]

        while folders_to_visit:
            folder_id = folders_to_visit.pop()

            batch = self._list_children(folder_id, image_query)
            files.extend(batch)
            logger.info(f"Listed {len(batch)} image(s) (total so far: {len(files)})")

            subfolders = self._list_children(folder_id, folder_query)
            folders_to_visit.extend(f["id"] for f in subfolders)

        return files

    def download_file(self, file_id: str, dest_path: str) -> bool:
        """Download a Drive file to dest_path. Returns True on success."""
        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(dest_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return True
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return False

    def get_view_url(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"

    def get_download_url(self, file_id: str) -> str:
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    def get_thumbnail_url(self, file_id: str, size: int = 400) -> str:
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{size}"
