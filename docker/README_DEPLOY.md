# 🚀 Deploy Nuxiva su Portainer (Git Stack)

Questo documento descrive come deployare Nuxiva su **Portainer** utilizzando un **Git Stack** con **OmniRoute** come gateway LLM centralizzato.

---

## 📋 Prerequisiti

1. **Portainer** installato e configurato
2. **OmniRoute** (o altro gateway OpenAI-compatible) in esecuzione sulla rete locale
3. **Chiave API di OmniRoute** con permessi di inferenza (formato `sk-...`)
4. Server Linux con Docker e Docker Compose

---

## 🔧 Configurazione Portainer Stack

### 1. Crea un nuovo Stack Git in Portainer

- **Nome Stack**: `nuxiva`
- **Repository URL**: URL del tuo repository Git (es. `https://github.com/your-org/nuxiva.git`)
- **Repository Reference**: `refs/heads/main` (o il branch desiderato)
- **Compose Path**: `docker/docker-compose.yml`

### 2. Configura le Variabili d'Ambiente

Nella sezione **"Environment variables"** di Portainer, aggiungi:

```env
# Network & Port
NUXIVA_PORT=8449

# LLM Provider (usa "openai" per OmniRoute)
LLM_PROVIDER=openai

# OmniRoute Endpoint (SENZA trailing slash)
OPENAI_BASE_URL=http://10.0.0.105:20128/v1

# API Key di OmniRoute (⚠️ OBBLIGATORIO)
OPENAI_API_KEY=sk-your-omniroute-inference-key

# Modello di default (opzionale)
DEFAULT_LLM_MODEL=Combinazione-Auto
```

### 3. Deploy dello Stack

1. Clicca su **"Deploy the stack"**
2. Attendi che Portainer cloni il repository e avvii i container
3. Verifica i log di `nuxiva-core` per confermare l'avvio corretto

---

## ✅ Verifica del Deploy

### Controllo Log

Apri i log del container `nuxiva-core` in Portainer e verifica:

```
✅ Embedding engine: OpenAI-compatible endpoint (http://10.0.0.105:20128/v1)
✅ Nuxiva v2.0.0 online — 8 agents, X graph nodes, Y graph edges
```

Se vedi:

```
❌ WARNING: Embedding model not found! Run: ollama pull nomic-embed-text
❌ Embedding engine: No embedding engine available!
```

Significa che:
- `OPENAI_API_KEY` non è configurata o non è valida
- OmniRoute non supporta `/v1/embeddings` → il sistema passerà automaticamente al fallback locale CPU

### Test API

```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://<server-ip>:8449/api/v1/health
```

### Test Web UI

Apri `http://<server-ip>:8449` nel browser e verifica che:
- La UI "Nuxiva Tactical OS" si carica correttamente
- I modelli vengono popolati nel menu a tendina "Team Agenti Operativo"
- Gli agenti rispondono alle richieste

---

## 🔄 Redeploy e Aggiornamenti

Per aggiornare Nuxiva dopo modifiche al codice:

1. Fai `git push` delle modifiche al repository
2. In Portainer, vai su **Stack → nuxiva → Update**
3. Clicca su **"Pull and redeploy"**
4. I volumi named (`nuxiva_db`, `nuxiva_qdrant`, ecc.) vengono preservati automaticamente

---

## 🧪 Modalità Debug

Per troubleshooting, aggiungi queste variabili d'ambiente:

```env
NUXIVA_ENV=development
LOG_LEVEL=DEBUG
```

Poi controlla i log per vedere:
- Discovery dei modelli: `GET http://10.0.0.105:20128/v1/models`
- Inferenza: `POST http://10.0.0.105:20128/v1/chat/completions`
- Embeddings: `POST http://10.0.0.105:20128/v1/embeddings`

---

## 🛡️ Sicurezza

- ⚠️ **NON salvare `OPENAI_API_KEY` nel repository Git**
- ✅ Configura sempre le chiavi tramite variabili d'ambiente di Portainer
- ✅ Usa named volumes per la persistenza dei dati
- ✅ Proteggi l'accesso a Portainer con autenticazione forte

---

## 📚 Provider Alternativi

Oltre a OmniRoute, puoi usare altri gateway OpenAI-compatible:

### LiteLLM
```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:4000/v1
OPENAI_API_KEY=sk-litellm-key
```

### vLLM
```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=dummy
```

### OpenAI Ufficiale
```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=  # Lascia vuoto per usare https://api.openai.com/v1
OPENAI_API_KEY=sk-your-openai-api-key
DEFAULT_LLM_MODEL=gpt-4o-mini
```

### Ollama Locale (senza autenticazione)
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OPENAI_API_KEY=  # Non necessario
```

---

## 🐛 Troubleshooting

### Problema: "401 Unauthorized" nei log

**Causa**: `OPENAI_API_KEY` mancante o errata

**Soluzione**: Verifica che la chiave sia configurata in Portainer e che sia una chiave di **inferenza** (non management) per OmniRoute.

### Problema: "embedding model returned no vector"

**Causa**: OmniRoute non supporta `/v1/embeddings` o il modello di embedding non è disponibile

**Soluzione**: Il sistema passa automaticamente al fallback locale CPU (`FastEmbed`). Nessuna azione richiesta, ma le performance potrebbero essere inferiori.

### Problema: UI vuota, nessun modello disponibile

**Causa**: Discovery dei modelli fallito (401 o timeout)

**Soluzione**:
1. Verifica che `OPENAI_BASE_URL` sia corretto (es. `http://10.0.0.105:20128/v1`)
2. Verifica che `OPENAI_API_KEY` sia valida
3. Testa manualmente: `curl -H "Authorization: Bearer sk-..." http://10.0.0.105:20128/v1/models`

---

## 📞 Supporto

Per ulteriori informazioni, consulta:
- [README principale](../README.md)
- [Documentazione OmniRoute](https://github.com/omniroute/omniroute)
- Log del container `nuxiva-core` in Portainer
