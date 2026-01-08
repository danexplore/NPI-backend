"""
Módulo de autenticação para Pipefy Service Accounts
Gerencia tokens OAuth 2.0 da API do Pipefy
"""

import os
import httpx
import logging
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
logger = logging.getLogger(__name__)

# Service Account Credentials
PIPEFY_SERVICE_ACCOUNT_ID = os.getenv("PIPEFY_SERVICE_ACCOUNT_ID")
PIPEFY_SERVICE_ACCOUNT_SECRET = os.getenv("PIPEFY_SERVICE_ACCOUNT_SECRET")

# Fallback para token legado (deprecated)
PIPEFY_API_KEY = os.getenv("PIPEFY_API_KEY")

# URLs
PIPEFY_OAUTH_URL = "https://app.pipefy.com/oauth/token"
PIPEFY_GRAPHQL_URL = "https://api.pipefy.com/graphql"

# Cache de token
_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None


def _validate_credentials():
    """Valida se as credenciais de autenticação estão configuradas"""
    if PIPEFY_SERVICE_ACCOUNT_ID and PIPEFY_SERVICE_ACCOUNT_SECRET:
        logger.info("✓ Usando Service Account do Pipefy")
        return "service_account"
    elif PIPEFY_API_KEY:
        logger.warning("⚠ Usando token legado do Pipefy (deprecated)")
        return "legacy_token"
    else:
        error_msg = (
            "❌ Credenciais do Pipefy não configuradas. "
            "Configure: PIPEFY_SERVICE_ACCOUNT_ID e PIPEFY_SERVICE_ACCOUNT_SECRET "
            "ou PIPEFY_API_KEY (deprecated)"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)


async def get_pipefy_token() -> str:
    """
    Obtém token de acesso OAuth 2.0 do Pipefy.
    Utiliza cache quando disponível.
    """
    global _cached_token, _token_expiry

    # Verificar se token em cache ainda é válido
    if _cached_token and _token_expiry and datetime.now() < _token_expiry:
        logger.debug("Usando token Pipefy do cache")
        return _cached_token

    # Se usar legacy token, retornar diretamente
    if PIPEFY_API_KEY and not PIPEFY_SERVICE_ACCOUNT_ID:
        logger.debug("Usando token legado (não há cache)")
        return PIPEFY_API_KEY

    # Obter novo token via OAuth 2.0
    if not PIPEFY_SERVICE_ACCOUNT_ID or not PIPEFY_SERVICE_ACCOUNT_SECRET:
        raise ValueError(
            "Service Account não configurado. "
            "Defina PIPEFY_SERVICE_ACCOUNT_ID e PIPEFY_SERVICE_ACCOUNT_SECRET"
        )

    try:
        async with httpx.AsyncClient() as client:
            logger.info("Obtendo novo token OAuth 2.0 do Pipefy")
            response = await client.post(
                PIPEFY_OAUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": PIPEFY_SERVICE_ACCOUNT_ID,
                    "client_secret": PIPEFY_SERVICE_ACCOUNT_SECRET,
                },
                timeout=10.0,
            )

            if not response.is_success:
                error_msg = f"Erro ao obter token Pipefy: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_msg,
                )

            data = response.json()
            _cached_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)  # Default 1 hora

            # Cachear token com 5 minutos de margem de segurança
            _token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)

            logger.info(f"✓ Token obtido com sucesso. Expira em {expires_in}s")
            return _cached_token

    except httpx.RequestError as e:
        error_msg = f"Erro de conexão ao obter token Pipefy: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


async def get_pipefy_headers() -> dict:
    """
    Retorna headers de autenticação para requisições ao Pipefy
    """
    try:
        token = await get_pipefy_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    except Exception as e:
        logger.error(f"Erro ao obter headers de autenticação: {str(e)}")
        raise


def get_pipefy_headers_sync() -> dict:
    """
    Versão síncrona para obter headers (para uso em contexto não-async)
    Nota: Use get_pipefy_headers() quando possível
    """
    if PIPEFY_API_KEY and not PIPEFY_SERVICE_ACCOUNT_ID:
        logger.debug("Usando token legado (contexto síncrono)")
        return {
            "Authorization": f"Bearer {PIPEFY_API_KEY}",
            "Content-Type": "application/json",
        }

    raise RuntimeError(
        "Headers síncronos requerem PIPEFY_API_KEY. "
        "Para Service Account, use get_pipefy_headers() (async)"
    )


# Validar credenciais ao importar
try:
    _auth_method = _validate_credentials()
    logger.info(f"Modo de autenticação Pipefy: {_auth_method}")
except ValueError as e:
    logger.error(str(e))
    raise


class PipefyAuthException(Exception):
    """Exceção específica para erros de autenticação Pipefy"""

    pass
