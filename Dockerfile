FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim-bookworm AS runtime-base
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates ffmpeg libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/backend/src \
    YOLO_CONFIG_DIR=/data/home/.config \
    MPLCONFIGDIR=/data/home/.cache/matplotlib YOLO_AUTOINSTALL=false
WORKDIR /app/backend

FROM runtime-base AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
FROM dependencies AS cpu-dependencies
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
FROM dependencies AS gpu-dependencies
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project --extra gpu

FROM runtime-base AS application
ENV HOME=/data/home
RUN groupadd --gid 10001 workbench && useradd --uid 10001 --gid 10001 --home-dir /data/home workbench \
    && mkdir -p /data/home/imports /data/home/.config /data/home/.cache \
    && chown -R workbench:workbench /data/home
COPY --chown=10001:10001 backend/src ./src
COPY --chown=10001:10001 backend/alembic ./alembic
COPY --chown=10001:10001 backend/alembic.ini ./alembic.ini
COPY --chown=10001:10001 deploy/worker.py /app/deploy/worker.py
EXPOSE 38000
USER 10001:10001
CMD ["uvicorn", "vision_dataset_workbench.main:app", "--host", "0.0.0.0", "--port", "38000", "--no-proxy-headers"]

FROM application AS cpu
COPY --from=cpu-dependencies /opt/venv /opt/venv

FROM application AS gpu
COPY --from=gpu-dependencies /opt/venv /opt/venv
USER root
# ONNX Runtime also needs the CUDA libraries installed by the locked PyTorch wheels.
RUN python -c 'from pathlib import Path; root=Path("/opt/venv/lib/python3.12/site-packages"); paths=[str(p) for p in (root/"nvidia").glob("*/lib")]+[str(root/"tensorrt_libs")]; Path("/etc/ld.so.conf.d/workbench-cuda.conf").write_text("\n".join(paths)+"\n")' && ldconfig
USER 10001:10001

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build
FROM nginx:1.28-alpine AS web
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
