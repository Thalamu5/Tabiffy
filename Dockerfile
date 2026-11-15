# One image for both the web/API server and the background worker.

FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# CPU-only PyTorch keeps the image much smaller. For an NVIDIA GPU, drop the index URL.
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu
COPY backend/ /app/backend/
RUN pip install --no-cache-dir "/app/backend[audio,separation,queue]" \
 && pip install --no-cache-dir --no-deps basic-pitch==0.4.0
# Download the Demucs model (~80 MB) at build time so the first song doesn't wait for it.
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')"
COPY --from=web /app/frontend/dist /app/frontend/dist
ENV TABIFFY_FRONTEND_DIST=/app/frontend/dist \
    TABIFFY_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "tabiffy.api:app", "--host", "0.0.0.0", "--port", "8000"]
