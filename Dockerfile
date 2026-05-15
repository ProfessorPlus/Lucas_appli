# Dockerfile racine — build de l'image backend pour Railway.
# Inclut backend/ + scripts/ (qui sont importés par le backend) +
# config/ (vide en prod, secrets téléchargés depuis Drive au startup).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OS deps pour reportlab, lxml, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev zlib1g-dev libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install backend deps first (cache layer)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# Copy backend + the legacy scripts/ it imports + writable dirs scaffolding
COPY backend /app/backend
COPY scripts /app/scripts
COPY assets /app/assets

# Writable dirs (config/data/Factures live in /tmp on Railway — ephemeral but ok,
# sources of truth are on Drive).
RUN mkdir -p /tmp/config /tmp/data /tmp/Factures

# Tell the legacy code we're "cloud" (uses Drive for I/O).
ENV PROFPLUS_CLOUD_MODE=true \
    PROFPLUS_DATA_DIR=/tmp/data \
    PROFPLUS_INVOICES_DIR=/tmp/Factures

# Railway provides PORT
ENV PORT=8000
EXPOSE 8000

WORKDIR /app/backend

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
