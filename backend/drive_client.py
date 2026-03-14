import os
import io
import logging
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
    "image/jpg",
    "image/png",
}


class DriveClient:
    def __init__(self):
        sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_path:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env")
        if not Path(sa_path).exists():
            raise FileNotFoundError(f"Service account JSON not found at: {sa_path}")

        credentials = service_account.Credentials.from_service_account_file(
            sa_path, scopes=SCOPES
        )
        self.service = build("drive", "v3", credentials=credentials)
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not self.folder_id:
            raise ValueError("GOOGLE_DRIVE_FOLDER_ID is not set in .env")

    def list_images(self) -> list[dict]:
        """List all image files in the configured Drive folder."""
        files = []
        page_token = None

        query = (
            f"'{self.folder_id}' in parents and trashed = false and ("
            + " or ".join(f"mimeType = '{m}'" for m in IMAGE_MIME_TYPES)
            + ")"
        )

        while True:
            params = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token

            response = self.service.files().list(**params).execute()
            batch = response.get("files", [])
            files.extend(batch)
            logger.info(f"Listed {len(batch)} files (total so far: {len(files)})")

            page_token = response.get("nextPageToken")
            if not page_token:
                break

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
