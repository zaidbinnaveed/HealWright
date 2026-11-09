# HealWright public demo: API + web app + live demo runs, for a Hugging Face Space (Docker SDK).
#
# The app listens on 7860 (HF's port); the Chaos Store for "Open the broken shop" runs
# internally on 127.0.0.1:8001 and is reached through the app under /shop. Public-safe mode
# (HEALWRIGHT_PUBLIC=1): VLM replay only (recorded replies, no keys), one demo at a time,
# per-visitor cooldown, no triage / patch apply / headed watch mode. See docs/RUNBOOK.md.

# --- 1. fonts (fetched at build time: the licence allows self-hosting, not redistribution)
FROM python:3.11-slim AS fonts
WORKDIR /src
RUN pip install --no-cache-dir "httpx==0.28.1"
COPY scripts/fetch_fonts.py scripts/fetch_fonts.py
RUN python scripts/fetch_fonts.py

# --- 2. the normal web app build
FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY --from=fonts /src/frontend/public/fonts ./public/fonts
RUN npm run build

# --- 3. runtime: the official Playwright image for the Playwright version locked in uv.lock
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-install-project
COPY . .
RUN uv sync --locked
COPY --from=web /src/frontend/dist ./frontend/dist

# Hugging Face runs the container as uid 1000: everything it writes lives under /tmp,
# and /app stays writable for pytest's own files (examples run from the repo root).
RUN chmod +x scripts/space_start.sh && chown -R 1000:1000 /app
ENV HOME=/tmp/home \
    HEALWRIGHT_PUBLIC=1 \
    HEALWRIGHT_VLM_MODE=replay \
    HEALWRIGHT_SHOP_URL=http://127.0.0.1:8001 \
    HEALWRIGHT_CORS_ORIGINS=https://healwright.vercel.app \
    HEALWRIGHT_ARTIFACT_DIR=/tmp/healwright \
    PORT=7860
USER 1000
EXPOSE 7860
CMD ["scripts/space_start.sh"]
