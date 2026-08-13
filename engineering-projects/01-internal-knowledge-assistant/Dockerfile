# =============================================================================
# UNTESTED: this image has never been built or run end to end.
#
# What is verified on the development machine:
#   - The Docker CLI is installed: `docker --version` reports 29.4.3.
#   - The daemon is unreachable: `docker run hello-world` fails with
#     "failed to connect to the docker API at
#      npipe:////./pipe/dockerDesktopLinuxEngine ... The system cannot find the
#      file specified", so no container has been run.
#   - Hardware virtualization support IS present. `systeminfo` reports all four
#     Hyper-V requirements as Yes: VM Monitor Mode Extensions, Virtualization
#     Enabled In Firmware, Second Level Address Translation, and Data Execution
#     Prevention Available. Hardware is therefore not the obstacle.
#
# The actual cause of the daemon not running remains unconfirmed.
#
# Every instruction below is written from the code's known requirements rather
# than verified by a successful build. Expect to iterate on the first real build.
# =============================================================================

FROM python:3.12-slim

WORKDIR /app

# Dependencies first, in their own layer, so that editing application code does
# not invalidate the cached pip install.
#
# requirements-api.txt, not requirements.txt: the service imports only fastapi,
# pydantic, cohere, python-dotenv, google-genai and qdrant-client (plus uvicorn
# to serve it). The full requirements.txt additionally carries streamlit, pypdf
# and tiktoken for the UI and the offline chunking scripts, which would be dead
# weight in this image.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Application code only. api.py imports rag_answer, and rag_answer imports
# nothing else local to this project, so these two files are the whole service.
COPY api.py rag_answer.py ./

# NOT copied into the image, deliberately:
#
#   qdrant_data/  - the vector store, ~40 MB and growing, and fully regenerable
#                   from the corpus by embed_and_store_structured.py. Baking it
#                   in would bloat every image layer with data that changes
#                   independently of the code. Mount it at run time instead:
#                       -v /host/path/qdrant_data:/app/qdrant_data
#                   The path must land at /app/qdrant_data, because rag_answer
#                   opens QDRANT_PATH as a path relative to the working dir.
#
#   .env          - holds GEMINI_API_KEY and COHERE_API_KEY. Secrets copied into
#                   an image persist in its layers and leak to anyone who can
#                   pull it, even if a later layer deletes the file. Supply them
#                   at run time instead:
#                       --env-file .env
#
# .dockerignore lists both (plus venv/ and __pycache__/) so that a stray
# `COPY . .` during future edits cannot pull them in by accident.
#
# Note: data/chunks_structured.json is also absent. The service does not need it
# in its default configuration - it is read lazily by get_bm25_index(), which
# only runs when answer_question is called with use_hybrid=True, and api.py does
# not enable hybrid retrieval. Mount or copy that file if hybrid is ever turned on.

EXPOSE 8000

# 0.0.0.0, not 127.0.0.1: binding to loopback inside a container makes the port
# unreachable from the host even when published.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
