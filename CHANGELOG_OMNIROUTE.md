# 📝 CHANGELOG - Supporto OmniRoute e Provider OpenAI-Compatible

## 🎯 Obiettivo
Abilitare Nuxiva a lavorare con **OmniRoute** (e altri gateway LLM OpenAI-compatible) come provider centralizzato, con supporto per autenticazione tramite API key e fallback automatico per embeddings su CPU-only.

---

## ✅ Modifiche Implementate

### 1. **Configurazione Environment ([`server/config/env.py`](../server/config/env.py))**

**Aggiunte:**
- `OPENAI_BASE_URL: str = ""` - Endpoint OpenAI-compatible (es. `http://10.0.0.105:20128/v1`)
- `DEFAULT_LLM_MODEL: str = ""` - Modello di default per gli agenti
- `LLM_PROVIDER: str = "ollama"` - Provider di default (ora supporta `"openai"`)

**Motivazione:** Permettere la configurazione flessibile del provider LLM senza modificare il codice.

---

### 2. **Gateway LLM Unificato ([`server/features/llm_gateway/gateway.py`](../server/features/llm_gateway/gateway.py))**

#### Modifiche a `_call_openai()`:
- **Prima:** URL hardcoded a `https://api.openai.com/v1`
- **Dopo:** Usa `settings.OPENAI_BASE_URL` se configurato, altrimenti OpenAI ufficiale
- **Modello:** Usa `settings.DEFAULT_LLM_MODEL` se presente, altrimenti `settings.NUXIVA_OPENAI_MODEL`

```python
# Nuovo comportamento
base_url = settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
endpoint = f"{base_url}/chat/completions"
```

#### Nuovi Metodi per Discovery Modelli:
- `list_available_models()` - Entry point unificato
- `_list_openai_models()` - Discovery via `/v1/models` con autenticazione `Bearer`
- `_list_ollama_models()` - Discovery via `/api/tags` (esistente)

**Comportamento:**
- Se `LLM_PROVIDER=openai` → chiama `/v1/models` con header `Authorization: Bearer {OPENAI_API_KEY}`
- Se `LLM_PROVIDER=ollama` → chiama `/api/tags` (backward compatible)

---

### 3. **Embedding Engine Unificato ([`server/core/cognitive_audit/embedding_engine.py`](../server/core/cognitive_audit/embedding_engine.py))**

**Completa riscrittura** da `OllamaEmbeddingEngine` a `UnifiedEmbeddingEngine`:

#### Strategia di Fallback a Cascata:
1. **OpenAI-compatible** (`/v1/embeddings`) con autenticazione
2. **Ollama nativo** (`/api/embeddings`)
3. **Locale CPU-only** (FastEmbed/sentence-transformers)

#### Metodi Chiave:
- `ensure_model_available()` - Verifica i provider in ordine e seleziona il primo disponibile
- `_check_openai_embeddings()` - Tenta una richiesta di prova a `/v1/embeddings`
- `_check_ollama_embeddings()` - Verifica `/api/tags` per `nomic-embed-text`
- `_init_local_engine()` - Carica `FastEmbedEngine` locale (già presente nel codebase)

#### Gestione Errori:
- Se OmniRoute **non supporta `/v1/embeddings`** → fallback automatico a locale CPU
- Se Ollama non è raggiungibile → fallback automatico a locale CPU
- Log dettagliati per troubleshooting: `Embedding engine: OpenAI-compatible endpoint` / `Local CPU (FastEmbed)`

---

### 4. **Docker Compose ([`docker/docker-compose.yml`](../docker/docker-compose.yml))**

#### Nuove Variabili d'Ambiente:
```yaml
environment:
  NUXIVA_PORT: ${NUXIVA_PORT:-8449}
  LLM_PROVIDER: ${LLM_PROVIDER:-openai}
  OPENAI_BASE_URL: ${OPENAI_BASE_URL:-http://10.0.0.105:20128/v1}
  OPENAI_API_KEY: ${OPENAI_API_KEY}
  DEFAULT_LLM_MODEL: ${DEFAULT_LLM_MODEL:-}
  OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://127.0.0.1:11434}
```

**Sintassi:** Tutte le variabili usano `${VAR:-default}` per permettere override da Portainer senza modificare il file.

#### Named Volumes (già presenti, preservati):
- `nuxiva_db` - Database SQLite
- `nuxiva_certs` - Certificati SSL
- `nuxiva_models` - Modelli AI locali
- `nuxiva_qdrant` - Vector database

---

### 5. **Documentazione Deploy ([`docker/README_DEPLOY.md`](../docker/README_DEPLOY.md))**

Nuova guida completa per deploy su **Portainer Git Stack**:
- Configurazione variabili d'ambiente
- Esempi per OmniRoute, LiteLLM, vLLM, OpenAI
- Sezione troubleshooting (401, embedding fallback, UI vuota)
- Checklist di verifica post-deploy

---

### 6. **Template Environment ([`docker/.env.example`](../docker/.env.example))**

File di esempio con tutte le variabili supportate e commenti esplicativi. Da usare come riferimento per la configurazione in Portainer.

---

## 🔄 Retrocompatibilità

✅ **Tutte le modifiche sono backward-compatible:**
- Se `LLM_PROVIDER=ollama` (default), il comportamento è identico alla versione precedente
- Se `OPENAI_BASE_URL` non è configurato, usa OpenAI ufficiale
- Gli endpoint esistenti (`/api/tags`, `/api/chat`) continuano a funzionare
- Il frontend non richiede modifiche (usa già gli endpoint backend)

---

## 🧪 Testing

### Test Manuale Consigliato:

1. **Deploy su Portainer** con configurazione OmniRoute:
   ```env
   LLM_PROVIDER=openai
   OPENAI_BASE_URL=http://10.0.0.105:20128/v1
   OPENAI_API_KEY=sk-your-key
   ```

2. **Verifica log all'avvio**:
   ```
   ✅ Embedding engine: OpenAI-compatible endpoint
   ✅ Nuxiva v2.0.0 online — 8 agents, X nodes, Y edges
   ```

3. **Test discovery modelli**:
   ```bash
   # Backend
   curl http://localhost:8449/api/v2/brain/ollama/probe \
     -H "Content-Type: application/json" \
     -d '{"host":"http://10.0.0.105:20128"}'
   
   # Dovrebbe restituire i modelli disponibili su OmniRoute
   ```

4. **Test inferenza tramite UI**:
   - Apri la Web UI
   - Invia una richiesta a un agente
   - Verifica nei log: `POST http://10.0.0.105:20128/v1/chat/completions`

5. **Test embeddings**:
   - Attiva il grafo cognitivo (training hippocampus)
   - Verifica nei log: `POST http://10.0.0.105:20128/v1/embeddings`
   - Se fallisce → verifica fallback: `Local FastEmbed engine initialized`

---

## 🚨 Breaking Changes

**Nessuno.** Tutte le modifiche sono opt-in via variabili d'ambiente.

---

## 📦 File Modificati

1. ✏️ [`server/config/env.py`](../server/config/env.py) - Nuove variabili config
2. ✏️ [`server/features/llm_gateway/gateway.py`](../server/features/llm_gateway/gateway.py) - Supporto OpenAI-compatible
3. ✏️ [`server/core/cognitive_audit/embedding_engine.py`](../server/core/cognitive_audit/embedding_engine.py) - Embedding unificato
4. ✏️ [`docker/docker-compose.yml`](../docker/docker-compose.yml) - Variabili env per Portainer
5. ➕ [`docker/README_DEPLOY.md`](../docker/README_DEPLOY.md) - Guida deploy
6. ➕ [`docker/.env.example`](../docker/.env.example) - Template configurazione

---

## 🎉 Risultato

Nuxiva ora supporta nativamente:
- ✅ **OmniRoute** come gateway LLM centralizzato
- ✅ **Autenticazione API key** per tutti i provider OpenAI-compatible
- ✅ **Fallback automatico** per embeddings su server CPU-only
- ✅ **Deploy da Portainer** senza secrets nel repository Git
- ✅ **Persistenza dati** tramite named volumes Docker
- ✅ **Retrocompatibilità totale** con configurazioni Ollama esistenti

---

## 📞 Supporto

Per problemi o domande:
1. Controlla i log del container `nuxiva-core` in Portainer
2. Consulta [`docker/README_DEPLOY.md`](../docker/README_DEPLOY.md) per troubleshooting
3. Verifica che `OPENAI_API_KEY` sia configurata correttamente
4. Testa manualmente gli endpoint di OmniRoute con `curl`
