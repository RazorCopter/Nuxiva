"""
Brain Center Controller - Gestisce discovery modelli e configurazione routing LLM.
Espone endpoint per l'interfaccia "Team Agenti Operativo" nella UI.
"""
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.features.llm_gateway.gateway import llm_gateway
from server.config.env import settings

logger = logging.getLogger("nuxiva.brain_center")

brain_center_router = APIRouter(prefix="/api", tags=["brain_center"])


class BrainOverviewResponse(BaseModel):
    """Risposta overview con lista modelli disponibili e configurazione"""
    pool: List[Dict[str, Any]]
    routing: Dict[str, Any]
    roles: List[Dict[str, Any]]
    catalog: List[Dict[str, Any]]
    error: str | None = None


@brain_center_router.get("/brains")
async def get_brain_overview() -> Dict[str, Any]:
    """
    Endpoint principale per Brain Center UI.
    Restituisce modelli disponibili e configurazione routing.
    
    Chiamato da: client_web/src/features/brain_center/core/brainApi.ts:fetchOverview()
    """
    try:
        # Usa il metodo list_available_models() dal gateway LLM
        models = await llm_gateway.list_available_models()
        
        if not models:
            error_msg = _build_error_message()
            logger.warning("Brain Center: Nessun modello disponibile. %s", error_msg)
            return {
                "pool": [],
                "routing": {},
                "roles": [],
                "catalog": [],
                "error": error_msg
            }
        
        # Costruisce il pool di modelli nel formato atteso dal frontend
        pool = [{"name": model, "label": model, "provider": _detect_provider(model)} for model in models]
        
        logger.info("Brain Center: %d modelli disponibili (%s)", len(models), settings.LLM_PROVIDER)
        
        return {
            "pool": pool,
            "routing": {"enabled": True, "provider": settings.LLM_PROVIDER},
            "roles": [],  # Gestito dinamicamente da brain_routing.py
            "catalog": _build_catalog(models),
            "error": None
        }
        
    except Exception as e:
        error_msg = f"Errore discovery modelli: {str(e)}"
        logger.error("Brain Center: %s", error_msg, exc_info=True)
        
        return {
            "pool": [],
            "routing": {},
            "roles": [],
            "catalog": [],
            "error": error_msg
        }


@brain_center_router.get("/brains/assignments")
async def get_brain_assignments() -> Dict[str, Any]:
    """
    Restituisce le assegnazioni modelli → agenti.
    
    Chiamato da: client_web/src/features/brain_center/core/brainApi.ts:fetchPool()
    """
    try:
        models = await llm_gateway.list_available_models()
        
        if not models:
            error_msg = _build_error_message()
            logger.warning("Brain Assignments: Nessun modello disponibile. %s", error_msg)
            return {
                "pool": [],
                "error": error_msg
            }
        
        pool = [{"name": model, "label": model} for model in models]
        
        return {
            "pool": pool,
            "error": None
        }
        
    except Exception as e:
        error_msg = f"Errore recupero assegnazioni: {str(e)}"
        logger.error("Brain Assignments: %s", error_msg, exc_info=True)
        
        return {
            "pool": [],
            "error": error_msg
        }


def _build_error_message() -> str:
    """Costruisce messaggio di errore dettagliato per debug"""
    provider = settings.LLM_PROVIDER
    
    if provider == "openai":
        if not settings.OPENAI_BASE_URL:
            return "OPENAI_BASE_URL non configurato. Configura la variabile d'ambiente in Portainer."
        if not settings.OPENAI_API_KEY:
            return "OPENAI_API_KEY non configurato. Configura la variabile d'ambiente in Portainer."
        return f"Impossibile recuperare modelli da {settings.OPENAI_BASE_URL}. Verifica: 1) URL corretto, 2) API key valida, 3) Endpoint raggiungibile."
    
    elif provider == "ollama":
        return f"Impossibile recuperare modelli da Ollama ({settings.OLLAMA_BASE_URL}). Verifica: 1) Ollama in esecuzione, 2) URL corretto, 3) Modelli installati (ollama list)."
    
    else:
        return f"Provider LLM '{provider}' non riconosciuto. Valori validi: 'openai', 'ollama'."


def _detect_provider(model_name: str) -> str:
    """Deduce il provider dal nome del modello"""
    if "/" in model_name or model_name.startswith("gpt-") or model_name.startswith("claude-"):
        return "openai"
    return "ollama"


def _build_catalog(models: List[str]) -> List[Dict[str, Any]]:
    """Costruisce il catalogo modelli per il frontend"""
    catalog = []
    for model in models:
        catalog.append({
            "name": model,
            "label": model,
            "category": "llm",
            "installed": True,
            "size_gb": None,
            "fit": {"level": "ok", "tps": None, "where": settings.LLM_PROVIDER},
            "license": {"warning": None},
        })
    return catalog
