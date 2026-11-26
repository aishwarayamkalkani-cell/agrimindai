#!/usr/bin/env bash
# Linux/macOS: backend on :8000 serving the built frontend. For frontend hot-reload run `npm run dev` in frontend/ (port 5173).
cd "$(dirname "$0")/backend" && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
