# Hardened non-root Python runtime for Render, Railway, Fly.io, or Cloud Run
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTAINER_RUNTIME=1 \
    CONCERT_TRACKER_HOST=0.0.0.0 \
    PORT=8080 \
    CONCERT_TRACKER_DATA_DIR=/app/data

RUN groupadd --system appgroup && useradd --system --gid appgroup --home /app appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appgroup app ./app
COPY --chown=appuser:appgroup scripts ./scripts
COPY --chown=appuser:appgroup static ./static
COPY --chown=appuser:appgroup server.py ./

RUN mkdir -p /app/data/uploads && chown -R appuser:appgroup /app/data && chmod 700 /app/data /app/data/uploads

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/api/healthz', timeout=3)" || exit 1

CMD ["python3", "-P", "server.py"]
