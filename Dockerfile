# AgriMind AI - lite production image (fits 512 MB RAM): FastAPI backend serving the built React frontend.
# No PyTorch / Sentence-Transformer; no model training during build or startup.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AGRIMIND_LITE=1 \
    EMBEDDING_BACKEND=tfidf \
    MALLOC_ARENA_MAX=2 \
    ONNX_THREADS=1 \
    OMP_NUM_THREADS=1 \
    PORT=8000

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY --chown=user:user . .
USER user
ENV AGRIMIND_STORE=/home/user/app/backend/storage

WORKDIR /home/user/app/backend
EXPOSE 8000
# Binds to the platform's $PORT (Render, Railway, Cloud Run...) on all interfaces.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
