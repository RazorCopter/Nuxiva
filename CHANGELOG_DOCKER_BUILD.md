# Changelog - Docker Build Architettura Originale Nuxiva

## [2024-11-03] - Ripristino Architettura Originale + Build Frontend

### 🎯 Problema Identificato
Il deployment Docker precedente:
1. ❌ **Non compilava il frontend** React (`client_web/`) → interfaccia web vuota/mancante
2. ❌ **Usava architettura semplificata** (`server/cmd/main.py`) invece del **supervisor originale** (`installer_wizard`)
3. ❌ **Porta singola** (8449) invece delle **porte multiple** dell'architettura originale (80, 8080, 8443)

### ✅ Correzione Applicata

#### 1. Dockerfile Riscritto con Multi-Stage Build
**File**: `docker/core/Dockerfile`

##### Stage 1: Frontend Builder
```dockerfile
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY client_web/package*.json ./
RUN npm ci --no-audit
COPY client_web/ ./
RUN npm run build
```

##### Stage 2: Nuxiva Supervisor Completo
```dockerfile
FROM python:3.11-slim-bookworm
ENV NUXIVA_DIR=/opt/Nuxiva \
    NUXIVA_PUBLIC_PORT=80 \
    NUXIVA_ADMIN_PORT=8080 \
    NUXIVA_CORE_URL=http://127.0.0.1:8443

# Copia installer_wizard (supervisor principale)
COPY installer_wizard ./installer_wizard
COPY server ./server
COPY scripts ./scripts

# Installa dipendenze
RUN pip install -r installer_wizard/backend/requirements.txt
RUN pip install -r server/requirements.txt

# Copia frontend compilato
COPY --from=frontend-builder /build/dist ./installer_wizard/web

CMD ["python", "-m", "installer_wizard.backend.nuxiva_launch"]
```

#### 2. Docker Compose Aggiornato
**File**: `docker/docker-compose.yml`

**Prima** (errato):
```yaml
network_mode: host
environment:
  NUXIVA_PORT: ${NUXIVA_PORT:-8449}
```

**Dopo** (architettura originale):
```yaml
ports:
  - "${NUXIVA_PUBLIC_PORT:-80}:80"      # Kiosk, chat, wizard
  - "${NUXIVA_ADMIN_PORT:-8080}:8080"   # Cockpit admin, API, MCP
  - "127.0.0.1:8443:8443"                # Core backend (localhost only)
environment:
  NUXIVA_PUBLIC_PORT: 80
  NUXIVA_ADMIN_PORT: 8080
  NUXIVA_CORE_URL: http://127.0.0.1:8443
```

#### 3. Documentazione Aggiornata
**File**: `docker/README_DEPLOY.md`, `docker/.env.example`

Documentata correttamente l'**architettura originale Nuxiva**:

| Porta | Descrizione | Riferimento Codice |
|-------|-------------|-------------------|
| **80** | Porta pubblica: kiosk, chat, wizard | `installer_wizard/backend/config.py:29` |
| **8080** | Porta admin: cockpit, REST API, MCP | `installer_wizard/backend/config.py:30` |
| **8443** | Core backend: supervisor, bus IPC | `installer_wizard/backend/config.py:31` |
| **11434** | Ollama: inferenza modelli locali | `installer_wizard/backend/config.py:32` |
| **6333** | Qdrant: vector database | `docker/docker-compose.yml` |

### 📖 Riferimento Repository Originale
Architettura basata su: [github.com/AprileNunzio/Nuxiva](https://github.com/AprileNunzio/Nuxiva)

### 🔄 Prossimi Passi per il Deploy

1. **Commit e Push**:
   ```bash
   git add docker/ CHANGELOG_DOCKER_BUILD.md
   git commit -m "fix: ripristina architettura originale Nuxiva con multi-stage build frontend"
   git push
   ```

2. **Redeploy su Portainer**:
   - Vai allo stack in Portainer
   - Clicca **"Pull and redeploy"** o **"Update the stack"**
   - Attendere rebuild completo (~5-10 minuti con frontend)

3. **Verifica Post-Deploy**:
   - **Porta 8444**: `http://10.0.0.105:8444` → Interfaccia pubblica (kiosk/wizard)
   - **Porta 8445**: `http://10.0.0.105:8445` → Cockpit admin (con autenticazione)

> **Nota**: Le porte 80 e 8080 erano già occupate su 10.0.0.105, quindi sono state mappate su 8444 e 8445 esternamente. Internamente il container usa comunque le porte standard 80/8080.

### ⚠️ Note Importanti

#### Differenze Rispetto al Deploy Precedente
| Aspetto | Prima (Errato) | Dopo (Corretto) |
|---------|---------------|----------------|
| **Supervisor** | `server/cmd/main.py` (semplificato) | `installer_wizard/backend/nuxiva_supervisor.py` (originale) |
| **Porte** | Singola porta 8449 | Multi-porta: 80, 8080, 8443 |
| **Frontend** | Non buildato | Compilato e copiato in `installer_wizard/web/` |
| **Architettura** | FastAPI standalone | Supervisor completo + Core backend separato |

#### Autenticazione Porta 8080
La porta admin (8080) nell'architettura originale richiede **autenticazione PAM** (root/admin). 
Nel container Docker potrebbe essere necessario configurare utenti/credenziali o disabilitare PAM per test.

### 🐛 Risoluzione ModuleNotFoundError: 'sandbox_broker' in Safe Mode
- **Causa**: All'avvio del container in Portainer, `nuxiva_launch` entrava in Safe Mode a causa del mancato modulo `sandbox_broker`, non incluso nelle direttive `COPY` del Dockerfile.
- **Soluzione**: Aggiunta la copia esplicita di `sandbox_broker`, `client_satellite` e del file `VERSION` in `/opt/Nuxiva` nel `Dockerfile` di runtime e aggiunto controllo di importazione `sandbox_broker` nello step di verifica build `RUN pip check && python -c ...`.
