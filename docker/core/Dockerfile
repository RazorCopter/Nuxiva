# Stage 1: Build frontend (client_web)
FROM node:20-slim AS frontend-builder

WORKDIR /build

COPY client_web/package*.json ./
RUN npm ci --no-audit

COPY client_web/ ./
RUN npm run build

# Stage 2: Nuxiva Supervisor completo (architettura originale)
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/Nuxiva \
    NUXIVA_DIR=/opt/Nuxiva \
    NUXIVA_PUBLIC_PORT=80 \
    NUXIVA_ADMIN_PORT=8080 \
    NUXIVA_CORE_URL=http://127.0.0.1:8443 \
    OLLAMA_URL=http://127.0.0.1:11434

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    libpam0g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/Nuxiva

# Copia installer_wizard (supervisor principale)
COPY installer_wizard ./installer_wizard

# Copia server (core backend)
COPY server ./server

# Copia scripts di sistema
COPY scripts ./scripts

# Installa dipendenze installer_wizard
RUN pip install -r installer_wizard/backend/requirements.txt

# Installa dipendenze server
RUN pip install -r server/requirements.txt

# Installa fastembed per embedding CPU-only
RUN pip install fastembed

# Verifica build
RUN pip check \
    && python -c "import fastapi, uvicorn, pydantic_settings; from cryptography.fernet import Fernet; key = Fernet.generate_key(); cipher = Fernet(key); assert cipher.decrypt(cipher.encrypt(b'nuxiva-build-check')) == b'nuxiva-build-check'"

# Copia frontend compilato in installer_wizard/web
COPY --from=frontend-builder /build/dist ./installer_wizard/web

# Crea directory per stato e configurazione
RUN mkdir -p /etc/nuxiva /var/lib/nuxiva /var/log/nuxiva

ARG NUXIVA_SRC_HASH=dev
LABEL org.nuxiva.src=$NUXIVA_SRC_HASH

# Esponi porte: 80 (public), 8080 (admin), 8443 (core backend)
EXPOSE 80 8080 8443

# Healthcheck su porta pubblica
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=4 \
    CMD curl -fsS "http://127.0.0.1:${NUXIVA_PUBLIC_PORT}/health" || exit 1

# Avvia supervisor con safe mode
CMD ["python", "-m", "installer_wizard.backend.nuxiva_launch"]
