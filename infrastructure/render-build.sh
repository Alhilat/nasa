#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -r requirements.lock
python -m pip install --no-deps -e ./backend -e ./data-pipeline
npm install --global pnpm@11.25.0
cd frontend
pnpm install --frozen-lockfile
VITE_API_BASE_URL=/api/v1 VITE_MAP_STYLE_URL= pnpm build
