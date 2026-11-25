#!/usr/bin/env bash
# Deploy (or update) the Hugging Face Space for this project.
#
#   hf auth login                        # once, with a token that has write access
#   ./deploy/deploy_space.sh             # or: ./deploy/deploy_space.sh your-name/your-space
#
# Uploads an allowlist of files only, so .env, .venv and tests never leave your computer.
# The prebuilt vector_db/ is included so the Space starts fast; if it's missing or out of date,
# the app rebuilds it on start-up.
set -euo pipefail

SPACE="${1:-C0derANANT/cravecart-assistant}"
cd "$(dirname "$0")/.."

if [ ! -f vector_db/rag_manifest.json ]; then
  echo "Building the vector DB first..."
  python ingest.py
fi

hf repos create "$SPACE" --repo-type space --space-sdk gradio --public --exist-ok

hf upload "$SPACE" . . --repo-type space \
  --include "app.py" --include "ingest.py" --include "requirements.txt" \
  --include "rag/*.py" --include "data/*.json" --include "knowledge-base/*" --include "vector_db/*" \
  --exclude "*.pyc" --exclude "*/__pycache__/*" --exclude "*.DS_Store" \
  --commit-message "Deploy Crave Assist"

hf upload "$SPACE" deploy/space-README.md README.md --repo-type space --commit-message "Space README"

echo "Deployed: https://huggingface.co/spaces/$SPACE"
echo "If this is the first deploy, add GROQ_API_KEY under Settings -> Variables and secrets."
