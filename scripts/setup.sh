#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from template. Remember to edit it with your secrets."
fi

echo "Setup complete. Activate the venv with 'source .venv/bin/activate' and run 'uvicorn app.main:app --reload'."
