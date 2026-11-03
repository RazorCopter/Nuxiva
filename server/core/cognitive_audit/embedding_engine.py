import logging
import os
from typing import List, Optional

import httpx
from server.config.env import settings

logger = logging.getLogger("nuxiva.embedding_engine")


class UnifiedEmbeddingEngine:
    """
    Motore di embedding unificato che supporta:
    1. Endpoint OpenAI-compatible (es. OmniRoute /v1/embeddings) con autenticazione
    2. Endpoint Ollama nativo (/api/embeddings)
    3. Fallback locale CPU-only con FastEmbed/sentence-transformers
    """

    def __init__(
        self,
        ollama_url: str = settings.OLLAMA_BASE_URL,
        openai_base_url: str = "",
        openai_api_key: str = "",
        default_model: str = settings.NUXIVA_EMBED_MODEL,
    ) -> None:
        self._ollama_url = ollama_url
        self._openai_base_url = openai_base_url or settings.OPENAI_BASE_URL
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "") or settings.OPENAI_API_KEY
        self._model = default_model
        self._use_openai = settings.LLM_PROVIDER.lower() == "openai" and bool(self._openai_base_url)
        self._local_engine: Optional[object] = None
        self._engine_type: str = "unknown"

    async def ensure_model_available(self) -> bool:
        """
        Verifica la disponibilità del modello di embedding.
        Ritorna True se almeno uno dei provider è disponibili.
        """
        # Prova prima OpenAI-compatible se configurato
        if self._use_openai:
            if await self._check_openai_embeddings():
                self._engine_type = "openai"
                logger.info("✅ Embedding engine: OpenAI-compatible endpoint (%s)", self._openai_base_url)
                return True
            logger.warning("❌ OpenAI-compatible embeddings non disponibili su %s - Verifica OPENAI_API_KEY e supporto /v1/embeddings", self._openai_base_url)

        # Prova Ollama nativo
        if await self._check_ollama_embeddings():
            self._engine_type = "ollama"
            logger.info("✅ Embedding engine: Ollama native (%s)", self._ollama_url)
            return True

        # Fallback locale CPU-only
        if self._init_local_engine():
            self._engine_type = "local"
            logger.info("✅ Embedding engine: Local CPU (FastEmbed) - Fallback attivo")
            return True

        logger.error("❌ ERRORE CRITICO: Nessun motore di embedding disponibile!")
        logger.error("   Soluzioni possibili:")
        logger.error("   1. Configura OPENAI_BASE_URL + OPENAI_API_KEY per /v1/embeddings")
        logger.error("   2. Avvia Ollama locale e installa: ollama pull %s", self._model)
        logger.error("   3. Installa fastembed per fallback CPU: pip install fastembed")
        return False

    async def _check_openai_embeddings(self) -> bool:
        """Verifica se l'endpoint OpenAI-compatible /v1/embeddings è raggiungibile"""
        if not self._openai_base_url or not self._openai_api_key:
            logger.debug("OpenAI embeddings: URL o API key mancanti")
            return False
        try:
            endpoint = f"{self._openai_base_url}/embeddings"
            headers = {"Authorization": f"Bearer {self._openai_api_key}"}
            # Prova una richiesta embedding minimale
            payload = {"model": self._model, "input": "test"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code == 401:
                    logger.warning("401 Unauthorized su %s - Verifica OPENAI_API_KEY", endpoint)
                    return False
                if response.status_code == 403:
                    logger.warning("403 Forbidden su %s - Chiave API potrebbe essere MANAGEMENT invece che INFERENCE", endpoint)
                    return False
                if response.status_code == 404:
                    logger.warning("404 Not Found su %s - OmniRoute potrebbe non supportare /v1/embeddings", endpoint)
                    return False
                if response.status_code == 502:
                    logger.warning("502 Bad Gateway su %s - OmniRoute non supporta /v1/embeddings", endpoint)
                    return False
                return response.status_code in (200, 400, 422)  # 400/422 = formato ok, modello forse mancante
        except httpx.TimeoutException:
            logger.warning("Timeout connessione a %s", endpoint)
            return False
        except httpx.ConnectError:
            logger.warning("Impossibile connettersi a %s", endpoint)
            return False
        except Exception as e:
            logger.debug("OpenAI embeddings check failed: %s", e)
            return False

    async def _check_ollama_embeddings(self) -> bool:
        """Verifica se Ollama /api/embeddings è disponibile"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._ollama_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    names = [m.get("name", "") for m in models]
                    if any(self._model in n for n in names):
                        return True
                    logger.warning(
                        "Model '%s' not found in Ollama. Run: ollama pull %s",
                        self._model,
                        self._model,
                    )
        except Exception as e:
            logger.debug("Ollama embeddings check failed: %s", e)
        return False

    def _init_local_engine(self) -> bool:
        """Inizializza engine locale FastEmbed o sentence-transformers"""
        try:
            from server.core.hippocampus_router.onnx_embedding_engine import FastEmbedEngine
            self._local_engine = FastEmbedEngine(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            # Verifica che si carichi correttamente chiamando ensure_dimension()
            dim_result = self._local_engine.ensure_dimension()
            
            # Gestione Result object (con metodi is_ok/unwrap)
            if hasattr(dim_result, 'is_ok'):
                if dim_result.is_ok:  # Proprietà, non metodo!
                    logger.info("Local FastEmbed engine initialized (dimension: %d)", dim_result.unwrap())
                    return True
                else:
                    logger.warning("FastEmbed dimension check failed: %s", dim_result.error if hasattr(dim_result, 'error') else 'unknown')
                    return False
            # Gestione int diretto
            elif isinstance(dim_result, int) and dim_result > 0:
                logger.info("Local FastEmbed engine initialized (dimension: %d)", dim_result)
                return True
            else:
                logger.warning("FastEmbed dimension check returned unexpected type: %s", type(dim_result))
                return False
        except Exception as e:
            logger.warning("Failed to initialize local embedding engine: %s", e, exc_info=True)
        return False

    async def embed(self, text: str) -> List[float]:
        """
        Genera il vettore di embedding per il testo dato.
        Usa il provider disponibile (OpenAI-compatible > Ollama > locale).
        """
        if self._engine_type == "openai":
            return await self._embed_openai(text)
        elif self._engine_type == "ollama":
            return await self._embed_ollama(text)
        elif self._engine_type == "local":
            return self._embed_local(text)
        else:
            raise RuntimeError("No embedding engine available")

    async def _embed_openai(self, text: str) -> List[float]:
        """Embedding via endpoint OpenAI-compatible (es. OmniRoute)"""
        endpoint = f"{self._openai_base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self._openai_api_key}"}
        payload = {"model": self._model, "input": text}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Formato OpenAI: {"data": [{"embedding": [...]}]}
            vector = data.get("data", [{}])[0].get("embedding", [])
        
        if not vector:
            raise ValueError("OpenAI-compatible embedding returned no vector")
        return [float(v) for v in vector]

    async def _embed_ollama(self, text: str) -> List[float]:
        """Embedding via Ollama nativo /api/embeddings"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._ollama_url}/api/embeddings",
                json={"model": self._model, "prompt": text}
            )
            response.raise_for_status()
            vector = response.json().get("embedding", [])
        
        if not vector:
            raise ValueError("Ollama embedding returned no vector")
        return [float(v) for v in vector]

    def _embed_local(self, text: str) -> List[float]:
        """Embedding locale CPU-only con FastEmbed"""
        if not self._local_engine:
            raise RuntimeError("Local embedding engine not initialized")
        
        result = self._local_engine.embed(text)
        if result.is_err():
            raise RuntimeError(f"Local embedding failed: {result.error}")
        
        return result.unwrap()


embedding_engine = UnifiedEmbeddingEngine()
