# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    DATABASE_PATH=/var/data/vyaparmitra.db \
    FLASK_ENV=production \
    FLASK_DEBUG=0 \
    HOST=0.0.0.0 \
    PORT=5000 \
    PYTHONPATH=/app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app /var/data

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend /src/frontend/dist /app/frontend/dist
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app /var/data

EXPOSE 5000
VOLUME ["/var/data"]
ENTRYPOINT ["/app/docker-entrypoint.sh"]
