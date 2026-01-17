#!/bin/bash

# Load env vars automatically
set -a
source "$(dirname "$0")/.env"
set +a

# Hapus secret lama jika ada (ignore error jika belum ada)
echo "y" | modal secret delete my-secrets || true

modal secret create my-secrets \
  GH_TOKEN="$GH_TOKEN" \
  HF_TOKEN="$HF_TOKEN" \
  CLOUDFLARED_TOKEN="$CLOUDFLARED_TOKEN" \
  CF_CLIENT_ID="$CF_CLIENT_ID" \
  CF_CLIENT_SECRET="$CF_CLIENT_SECRET" \
  API_URL="$API_URL" \
  API_KEY="$API_KEY" \
  SSH_KEY="$SSH_KEY"

