# Imagen del backend (FastAPI, Python 3.12). El backend corre siempre en Docker (ADR-016).
# Contexto de build: raíz del repositorio (ver infra/docker-compose.yml).

# --- base: sistema operativo y librerías nativas -----------------------------------------
FROM python:3.12.7-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Pango y HarfBuzz para WeasyPrint (ADR-010) y fuentes para los PDF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
# Carpeta de STORAGE_BACKEND=local (volumen `api-storage`): de `app`, para que un volumen nuevo
# herede ese dueño (Docker copia el dueño de la imagen al crearlo). Sin esto, la API —que corre
# como `app`— no puede escribir los archivos subidos (S2-06).
RUN mkdir -p /data/storage && chown app:app /data/storage
WORKDIR /app

# --- dev: dependencias de desarrollo; el código se monta como volumen ----------------------
# Contrato con S1-03: el backend declara sus dependencias en backend/requirements.txt y
# backend/requirements-dev.txt (este último incluye "-r requirements.txt").
FROM base AS dev
COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# La etapa de producción (sin recarga, código copiado en la imagen) se agrega en F10 (DP-05).
