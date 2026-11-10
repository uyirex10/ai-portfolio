FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY playbook.yaml .
# .cache/ (demo-only hand-authored responses) is intentionally NOT copied --
# a deployed instance should make real calls against a real API key, not
# replay scripts/seed_demo_cache.py's stand-in content.

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
