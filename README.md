# Event Photo Finder

A web app where event guests upload a selfie and instantly receive all event photos containing their face. Photos are stored in Google Drive and matched using AI face recognition.

Works for any event — weddings, conferences, birthday parties, corporate gatherings, and more.

---

## How It Works

1. Run the **indexer** once to scan all photos in your Google Drive folder and build a face embeddings index.
2. Start the **backend server**.
3. Guests open the web app, upload a selfie, and see every photo they appear in — with download links.

---

## Prerequisites

- Python 3.9+
- Node.js 18+ (for the React frontend)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Google Cloud project with the Drive API enabled
- Event photos in a Google Drive folder

---

## Google Drive Setup

### 1. Create a Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **New Project**, give it a name (e.g. "Event Photo Finder"), and create it.

### 2. Enable the Google Drive API
1. In your project, go to **APIs & Services → Library**
2. Search for "Google Drive API" and click **Enable**

### 3. Create a Service Account
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Give it a name (e.g. "event-photo-finder"), click **Create and Continue**
4. Skip optional role/access fields and click **Done**
5. Click the service account you just created
6. Go to the **Keys** tab → **Add Key → Create new key → JSON**
7. The JSON file downloads automatically — keep it safe and **never commit it** (`.gitignore` already excludes `*.json` and `.env`)

### 4. Share Your Drive Folder With the Service Account
1. Copy the service account email (looks like `name@project.iam.gserviceaccount.com`)
2. In Google Drive, right-click your event photos folder → **Share**
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
cd event-photo-finder

# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && npm install && cd ..
```

> **Note:** InsightFace will automatically download the `buffalo_l` model (~200 MB) on first run. Ensure you have an internet connection.

---

## Configuration

Edit `.env` in the project root:

```env
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/your/service_account.json
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here

# UI branding (shown in the app header)
EVENT_NAME=My Event
EVENT_SUBTITLE=Find all your photos from this event

# Match tuning
SIMILARITY_THRESHOLD=0.4   # Lower = more matches (less strict). Range: 0.0 – 1.0
MAX_RESULTS=50             # Max photos returned per search (0 = unlimited)

# Abuse protection — limits how often one IP can call /api/match,
# since face matching is CPU-intensive. Format: "<count>/<period>",
# e.g. "6/minute", "100/hour".
MATCH_RATE_LIMIT=6/minute
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

**Development** (two terminals, with hot reload):
```bash
# Terminal 1 — Python backend
uv run uvicorn backend.main:app --reload

# Terminal 2 — React frontend (Vite dev server on :5173)
cd frontend && npm run dev
```

**Production** (build frontend, serve everything from FastAPI):
```bash
cd frontend && npm run build && cd ..
uv run uvicorn backend.main:app --workers 4
```

Use `--workers` equal to your CPU core count. Each worker loads the model and index independently.

Open your browser at **http://localhost:8000** (production) or **http://localhost:5173** (dev).

---

## Project Structure

```
event-photo-finder/
├── backend/
│   ├── main.py               # FastAPI app (API routes + static serving)
│   ├── face_engine.py        # InsightFace embedding + cosine similarity
│   ├── drive_client.py       # Google Drive API client
│   ├── indexer.py            # One-time indexing script
│   └── embeddings_index.pkl  # Auto-generated after indexing
├── frontend/
│   ├── package.json          # React + Vite dependencies
│   ├── vite.config.js        # Dev server proxy config
│   ├── index.html            # Vite entry point
│   └── src/
│       ├── App.jsx           # Main state machine
│       ├── App.css           # Design system
│       └── components/       # Header, UploadCard, Results, SettingsPanel, …
├── temp/                     # Temp download folder (auto-cleaned after indexing)
├── deploy/
│   ├── setup-ec2.sh          # One-time EC2 provisioning (Docker install)
│   ├── reindex.service       # systemd unit — rebuilds the index
│   └── reindex.timer         # systemd timer — runs reindex nightly
├── Caddyfile                 # Reverse proxy + auto HTTPS config (AWS deploy)
├── docker-compose.yml
├── pyproject.toml            # uv project manifest
├── .gitignore
├── .env                      # Your credentials and config (never committed)
└── README.md
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/status` | Index status (total photos, faces, last indexed) |
| `GET` | `/api/config` | UI configuration (event name, subtitle) |
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

**Change the event name and subtitle:**

Set them in `.env` for permanent server-side defaults:
```env
EVENT_NAME=Sarah & James — Wedding 2025
EVENT_SUBTITLE=Find all your photos from our special day
```

Or change them live from within the app by clicking the **⚙ gear icon** in the top-right corner. Settings are saved in the browser's localStorage and override the server defaults.

**Adjust match sensitivity:**
- Increase `SIMILARITY_THRESHOLD` (e.g. `0.5`) for stricter / fewer matches
- Decrease it (e.g. `0.3`) to cast a wider net

---

## AWS Deployment

This deploys the app on a single EC2 instance using Docker Compose, with
[Caddy](https://caddyserver.com/) as a reverse proxy providing free,
auto-renewing HTTPS via Let's Encrypt. HTTPS is required for the in-browser
camera capture feature to work for guests.

Since a custom domain isn't required, this uses [sslip.io](https://sslip.io)
— a free wildcard DNS service that maps any hostname containing
`<ip-with-dashes>` back to that IP address (e.g.
`rishabhwedspooja.54-123-45-67.sslip.io` → `54.123.45.67`), which is enough
for Let's Encrypt to issue a certificate. This lets you pick a friendly
prefix instead of being stuck with `photos-<ip>.sslip.io`.

### 0. Prerequisite: share your Drive folder publicly

Guests' browsers load photo thumbnails/downloads directly from Google Drive
(not proxied through your server), so the folder must be link-shareable:

1. In Google Drive, right-click your event photos folder → **Share**
2. Under **General access**, change to **Anyone with the link** → **Viewer**

Anyone with a direct file link could then view that photo — acceptable for
most events, but worth being aware of.

### 1. Launch the EC2 instance

1. AWS Console → **EC2** → **Launch instance**
2. AMI: **Ubuntu Server 24.04 LTS**
3. Instance type: **t3.small** (2 vCPU / 2 GB RAM — enough for InsightFace
   under moderate guest load)
4. Storage: 20 GB gp3 is plenty
5. Security group:
   - SSH (22) — restrict to **your IP only**
   - HTTP (80) and HTTPS (443) — **anywhere** (needed for Let's Encrypt + guests)
6. Launch, then **allocate an Elastic IP** and associate it with the instance
   (so the IP doesn't change on reboot — important since it's baked into
   your sslip.io hostname)

### 2. Set up the server

SSH into the instance, then run the setup script (installs Docker + Compose):

```bash
curl -fsSL https://raw.githubusercontent.com/<your-fork>/event-photo-finder/main/deploy/setup-ec2.sh -o setup-ec2.sh
bash setup-ec2.sh <your-repo-url>
```

(Or `scp` your project directory to the instance instead of cloning.)

Log out and back in (so the `docker` group membership applies), then `cd ~/event-photo-finder`.

### 3. Configure

1. Upload your service account key:

   ```bash
   scp service_account.json <ec2-host>:~/event-photo-finder/secrets/
   ```

2. Create `.env` (see [Configuration](#configuration) above) with your
   `GOOGLE_DRIVE_FOLDER_ID`, `EVENT_NAME`, etc.
3. Edit [Caddyfile](Caddyfile): replace the hostname with a prefix of your
   choice plus your Elastic IP (dots replaced by dashes) —
   e.g. `54.123.45.67` → `rishabhwedspooja.54-123-45-67.sslip.io`

### 4. Build the index and start the app

```bash
docker compose run --rm indexer   # builds the face embeddings index
docker compose up -d --build      # starts the app + Caddy
```

Visit `https://<your-chosen-prefix>.<your-elastic-ip-with-dashes>.sslip.io` —
Caddy will automatically obtain a TLS certificate on first request.

### 5. Keep the index up to date

New photos added to Drive won't show up until the index is rebuilt. Install
the provided systemd timer to rebuild it automatically every night at 4 AM:

```bash
sudo cp deploy/reindex.service deploy/reindex.timer /etc/systemd/system/
sudo systemctl enable --now reindex.timer
```

Adjust `User=` and `WorkingDirectory=` in `reindex.service` if you deployed
under a different user or path. To trigger an immediate rebuild:
`sudo systemctl start reindex.service`.

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
- Run `uv sync` to make sure all Python dependencies are installed
- Run `cd frontend && npm install` to make sure frontend dependencies are installed
- On Apple Silicon Macs, `onnxruntime` in `pyproject.toml` is already the correct CPU-only build

**Thumbnails not loading in the browser**
- Google Drive thumbnails require the photos to be accessible. Ensure the Drive folder is not restricted beyond the service account.
- Alternatively, make the Drive folder link-shareable (view-only) so thumbnails load in browsers without authentication.
