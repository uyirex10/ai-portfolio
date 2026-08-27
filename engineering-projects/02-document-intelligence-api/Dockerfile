# Built by Render from this file, not locally. Docker Desktop is not viable on the
# development machine - diagnosed rather than assumed: BIOS virtualization, firmware,
# WSL2 prerequisites and the daemon's own backend config all check out, and there is a
# separate RAM constraint that would bite even if the daemon started. Render builds the
# image server-side, so a working container is still a real deliverable; it is just not
# one that gets built here first.
#
# The consequence for this file: every instruction is written from the code's known
# imports and the platform's documented contract, and the first real build is the first
# time it runs. The PORT binding below is the one Render-specific detail.

FROM python:3.12-slim

# PYTHONUNBUFFERED so logs reach Render's log stream as they happen rather than sitting
# in a buffer; PYTHONDONTWRITEBYTECODE because .pyc files in a container are dead weight
# written once and never reused.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies in their own layer, before the application code, so editing a module
# does not invalidate the cached pip install.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code, listed explicitly. A blanket `COPY . .` would pull in .env, the
# local venv and the SQLite request log; .dockerignore covers those too, but being
# explicit here means the image contents are a decision rather than a leftover.
COPY api.py auth.py confidence.py config.py documents.py extraction.py \
     models.py pipeline.py ratelimit.py requestlog.py usage.py ./
COPY templates/ ./templates/

# Not copied, deliberately:
#
#   .env       - holds GEMINI_API_KEY and the client API keys. Secrets baked into an
#                image persist in its layers and leak to anyone who can pull it, even
#                if a later layer deletes the file. Set them as environment variables
#                in the Render dashboard instead.
#   requests.db - the request log. Written at run time; shipping one would mean the
#                image carries someone else's traffic history.
#   test_*.py  - the suites run before the image is built, not inside it.

# Documentation only. Render ignores EXPOSE and routes to whatever $PORT names.
EXPOSE 8000

# Render injects PORT and expects the process to bind it; a hardcoded port gets the
# service marked unhealthy and cycled. Defaulted so `docker run -p 8000:8000` still
# works locally with no environment set.
#
# Shell form on purpose - the exec form would pass the literal string "$PORT" to
# uvicorn, since there is no shell to expand it.
#
# 0.0.0.0, not 127.0.0.1: binding loopback inside a container makes the port
# unreachable from outside it even when published.
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
