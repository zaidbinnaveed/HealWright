#!/bin/sh
# Container entrypoint (Dockerfile): the internal Chaos Store on 127.0.0.1:8001 for
# "Open the broken shop" (reached through the app under /shop), then the HealWright app
# (API + web app) in public-safe mode on 0.0.0.0:$PORT.
set -eu
mkdir -p "$HOME" "$HEALWRIGHT_ARTIFACT_DIR"
CHAOS_CONTROL=1 /app/.venv/bin/uvicorn chaos_store.app:create_app --factory \
    --host 127.0.0.1 --port 8001 --log-level warning &
exec /app/.venv/bin/healwright serve --host 0.0.0.0 --port "${PORT:-7860}"
