# Wedding Photo Finder

A web app where wedding guests upload a selfie and instantly receive all wedding photos containing their face. Photos are stored in Google Drive and matched using AI face recognition.

---

## How It Works

1. Run the **indexer** once to scan all photos in your Google Drive folder and build a face embeddings index.
2. Start the **backend server**.
3. Guests open the web app, upload a selfie, and see every photo they appear in — with download links.

---

## Prerequisites

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Google Cloud project with the Drive API enabled
- Wedding photos in a Google Drive folder

---

## Google Drive Setup

### 1. Create a Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **New Project**, give it a name (e.g. "Wedding Photo Finder"), and create it.

### 2. Enable the Google Drive API
1. In your project, go to **APIs & Services → Library**
2. Search for "Google Drive API" and click **Enable**

### 3. Create a Service Account
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Give it a name (e.g. "wedding-photo-finder"), click **Create and Continue**
4. Skip optional role/access fields and click **Done**
5. Click the service account you just created
6. Go to the **Keys** tab → **Add Key → Create new key → JSON**
7. The JSON file downloads automatically — keep it safe and **never commit it** (`.gitignore` already excludes `*.json` and `.env`)

### 4. Share Your Drive Folder With the Service Account
1. Copy the service account email (looks like `name@project.iam.gserviceaccount.com`)
2. In Google Drive, right-click your wedding photos folder → **Share**
3. Paste the service account email and give it **Viewer** access
4. Click **Share**

### 5. Get the Folder ID
Open the folder in Google Drive — the URL will look like:
```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                        This is your FOLDER_ID
```

---

## Installation

```bash
# Clone / navigate to the project
cd wedding-photo-finder

# Create a virtual environment and install all dependencies
uv sync
```

This creates a `.venv` folder and installs everything from `pyproject.toml` in one step.

> **Note:** InsightFace will automatically download the `buffalo_l` model (~200 MB) on first run. Ensure you have an internet connection.

---

## Configuration

Edit `.env` in the project root:

```env
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/your/service_account.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
SIMILARITY_THRESHOLD=0.4   # Lower = more matches (less strict). Range: 0.0 – 1.0
MAX_RESULTS=50             # Max photos returned per search
```

---

## Building the Index

Run this once before starting the server, and re-run whenever new photos are added to Drive:

```bash
uv run python backend/indexer.py
```

Output example:
```
==================================================
Indexing complete!
  Photos processed : 312
  Faces detected   : 748
  Skipped photos   : 4
  Index saved to   : backend/embeddings_index.pkl
==================================================
```

---

## Starting the Server

**Development** (single process, auto-reload):
```bash
uv run uvicorn backend.main:app --reload
```

**Production / high traffic** (multiple worker processes):
```bash
uv run uvicorn backend.main:app --workers 4
```

Use `--workers` equal to your CPU core count. Each worker loads the model and index independently, so 4 workers can handle 4 simultaneous face inference jobs in parallel.

Open your browser at **http://localhost:8000**

---

## Project Structure

```
wedding-photo-finder/
├── backend/
│   ├── main.py               # FastAPI app (API routes + static serving)
│   ├── face_engine.py        # InsightFace embedding + cosine similarity
│   ├── drive_client.py       # Google Drive API client
│   ├── indexer.py            # One-time indexing script
│   ├── embeddings_index.pkl  # Auto-generated after indexing
│   └── requirements.txt      # For reference (pyproject.toml is authoritative)
├── frontend/
│   └── index.html            # Single-page UI (no framework)
├── temp/                     # Temp download folder (auto-cleaned after indexing)
├── pyproject.toml            # uv project manifest
├── .gitignore                # Excludes .env, *.json, .venv, embeddings index
├── .env                      # Your credentials and config (never committed)
└── README.md
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve the frontend |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/status` | Index status (total photos, faces, last indexed) |
| `POST` | `/api/match` | Upload selfie, get matching photos |

### POST /api/match

**Request:** `multipart/form-data` with field `selfie` (image file)

**Response:**
```json
{
  "success": true,
  "matched_count": 12,
  "photos": [
    {
      "file_id": "abc123",
      "filename": "photo_001.jpg",
      "view_url": "https://drive.google.com/file/d/abc123/view",
      "download_url": "https://drive.google.com/uc?export=download&id=abc123",
      "similarity_score": 0.87,
      "thumbnail_url": "https://drive.google.com/thumbnail?id=abc123&sz=w400"
    }
  ]
}
```

---

## Customization

**Change wedding couple names:**
Edit the `<h1>` tag in `frontend/index.html`:
```html
<h1><em>Sarah</em> &amp; <em>James</em></h1>
```

**Adjust match sensitivity:**
- Increase `SIMILARITY_THRESHOLD` (e.g. `0.5`) for stricter / fewer matches
- Decrease it (e.g. `0.3`) to cast a wider net

---

## Troubleshooting

**"No face detected in selfie"**
- Ensure the selfie has a clear, well-lit face
- Avoid heavy filters, sunglasses, or extreme angles
- Try a different photo

**Google Drive auth errors**
- Double-check the path in `GOOGLE_SERVICE_ACCOUNT_JSON`
- Confirm the service account has been shared on the correct Drive folder
- Ensure the Google Drive API is enabled in your Cloud project

**Index is empty / no photos found after indexing**
- Verify `GOOGLE_DRIVE_FOLDER_ID` is correct (just the ID, not the full URL)
- Check that photos are directly inside the folder (not in sub-folders)
- Confirm the service account email was added as a Viewer to the folder

**Server not starting**
- Run `uv sync` to make sure all dependencies are installed
- On Apple Silicon Macs, `onnxruntime` in `pyproject.toml` is already the correct CPU-only build

**Thumbnails not loading in the browser**
- Google Drive thumbnails require the photos to be accessible. Ensure the Drive folder is not restricted beyond the service account.
- Alternatively, make the Drive folder link-shareable (view-only) so thumbnails load in browsers without authentication.
