#!/usr/bin/env bash
#
# One-time setup for a fresh Ubuntu 24.04 EC2 instance.
#
# Usage (after SSH-ing into the instance):
#   curl -fsSL https://raw.githubusercontent.com/<your-fork>/event-photo-finder/main/deploy/setup-ec2.sh | bash
#   -- or --
#   bash deploy/setup-ec2.sh [git-repo-url]
#
# What this does:
#   1. Installs Docker Engine + the Compose plugin from Docker's official repo.
#   2. Adds the current user to the `docker` group (re-login required).
#   3. Clones the project repo (if a URL is given) or creates an empty
#      ~/event-photo-finder directory for you to upload files into.

set -euo pipefail

REPO_URL="${1:-}"
APP_DIR="$HOME/event-photo-finder"

echo "==> Installing Docker Engine + Compose plugin..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> Adding $USER to the docker group..."
sudo usermod -aG docker "$USER"

echo "==> Setting up application directory..."
if [ -n "$REPO_URL" ]; then
  if [ -d "$APP_DIR" ]; then
    echo "    $APP_DIR already exists, skipping clone."
  else
    git clone "$REPO_URL" "$APP_DIR"
  fi
else
  mkdir -p "$APP_DIR/secrets"
  echo "    Created $APP_DIR (no repo URL given — upload your project files here)."
fi

cat <<'EOF'

==================================================================
Docker installed. Log out and back in (or run `newgrp docker`)
for the group change to take effect, then:

  1. Upload your Google service account key:
       scp service_account.json <ec2-host>:~/event-photo-finder/secrets/

  2. Create ~/event-photo-finder/.env (see .env example in README).

  3. Edit Caddyfile: replace the placeholder hostname with
       photos-<elastic-ip-with-dashes>.sslip.io
     e.g. an Elastic IP of 54.123.45.67 ->
       photos-54-123-45-67.sslip.io

  4. Build the photo index (run once, and again whenever new
     photos are added to Drive):
       cd ~/event-photo-finder
       docker compose run --rm indexer

  5. Start the app:
       docker compose up -d --build

  6. Visit https://photos-<elastic-ip-with-dashes>.sslip.io
==================================================================
EOF
