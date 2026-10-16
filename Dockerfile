# Strud AI — FastAPI backend container for hosted deployments (Render).
#
# Build context is the REPOSITORY ROOT (config.py must be importable):
#   docker build -t strud-backend .
#   docker run -p 8000:8000 -e STRUD_DATA_DIR=/data -v strud-data:/data strud-backend
#
# Notes:
# - sentence-transformers (torch) is intentionally NOT installed: the
#   retrieval pipeline auto-degrades to the sparse legs (TF-IDF + BM25)
#   when the dense embeddings library is absent (documented fallback).
#   A dense-capable image can be built later by adding it here.
# - No secrets are baked into this image; all provider/model credentials
#   arrive at runtime via environment variables (see render.yaml notes).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY strud/backend/requirements.txt ./strud/backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r strud/backend/requirements.txt

COPY . .

ENV STRUD_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000

CMD ["sh", "-c", "uvicorn strud.backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
