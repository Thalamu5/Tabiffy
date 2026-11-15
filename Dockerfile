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
COPY backend/ /app/backend/
RUN pip install --no-cache-dir "/app/backend[audio,queue]" \
 && pip install --no-cache-dir --no-deps basic-pitch==0.4.0
COPY --from=web /app/frontend/dist /app/frontend/dist
ENV TABIFFY_FRONTEND_DIST=/app/frontend/dist \
    TABIFFY_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "tabiffy.api:app", "--host", "0.0.0.0", "--port", "8000"]
