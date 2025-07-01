"""
Routers para endpoints de monitoramento, métricas e health checks.
Inclui endpoints administrativos para observabilidade da API.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasicCredentials

from ..config import api_config, ERROR_MESSAGES, HTTP_STATUS
from ..middleware.monitoring import get_metrics, get_health_status, metrics_collector
from ..utils.cache import get_cache_manager, get_cache
from ..utils.logging import app_logger, api_logger
from ..main import verify_basic_auth  # Import da função de auth

# Router para endpoints de monitoramento
monitoring_router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

# Router para endpoints administrativos
admin_router = APIRouter(prefix="/admin", tags=["Administration"])

@monitoring_router.get("/health")
async def health_check():
    """
    Endpoint básico de health check.
    Não requer autenticação para uso por load balancers.
    """
    try:
        health_status = await get_health_status()
        
        # Determina status code baseado na saúde
        status_code = 200
        if health_status["status"] == "unhealthy":
            status_code = 503
        elif health_status["status"] == "degraded":
            status_code = 200  # Ainda funcional, mas degradado
        
        return JSONResponse(
            content=health_status,
            status_code=status_code
        )
    
    except Exception as e:
        app_logger.error("Health check failed", error=e)
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": "Health check failed",
                "message": str(e)
            },
            status_code=503
        )

@monitoring_router.get("/health/detailed")
async def detailed_health_check(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Endpoint detalhado de health check com métricas completas.
    Requer autenticação.
    """
    try:
        health_status = await get_health_status()
        return health_status
    except Exception as e:
        app_logger.error("Detailed health check failed", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@monitoring_router.get("/metrics")
async def get_api_metrics(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Endpoint para obter métricas da API.
    """
    try:
        metrics = get_metrics()
        api_logger.log_endpoint_call("get_metrics", credentials.username)
        return metrics
    except Exception as e:
        app_logger.error("Failed to get metrics", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@monitoring_router.get("/metrics/cache")
async def get_cache_metrics(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Endpoint para obter métricas específicas do cache.
    """
    try:
        cache_manager = get_cache_manager()
        cache_info = await cache_manager.get_cache_info()
        
        api_logger.log_endpoint_call("get_cache_metrics", credentials.username)
        return cache_info
    except Exception as e:
        app_logger.error("Failed to get cache metrics", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@monitoring_router.get("/status")
async def get_system_status():
    """
    Endpoint público de status do sistema.
    Retorna informações básicas sem dados sensíveis.
    """
    try:
        metrics = get_metrics()
        return {
            "status": "operational",
            "version": api_config.VERSION,
            "uptime_seconds": metrics["system"]["uptime_seconds"],
            "total_requests": metrics["requests"]["total"],
            "error_rate": metrics["requests"]["error_rate"]
        }
    except Exception as e:
        app_logger.error("System status check failed", error=e)
        return {
            "status": "degraded",
            "version": api_config.VERSION,
            "error": "Unable to retrieve full status"
        }

# ========== ENDPOINTS ADMINISTRATIVOS ==========

@admin_router.post("/cache/clear")
async def clear_cache(
    cache_group: Optional[str] = None,
    credentials: HTTPBasicCredentials = Depends(verify_basic_auth)
):
    """
    Limpa cache por grupo ou completamente.
    
    Args:
        cache_group: Grupo específico (courses, users, g2) ou None para tudo
    """
    try:
        cache_manager = get_cache_manager()
        
        if cache_group:
            # Limpa grupo específico
            results = await cache_manager.refresh_cache_group(cache_group)
            message = f"Cache group '{cache_group}' cleared"
        else:
            # Limpa todo o cache
            cache = get_cache()
            success = await cache.flush_all()
            results = {"flush_all": success}
            message = "All cache cleared"
        
        api_logger.log_endpoint_call("clear_cache", credentials.username, cache_group=cache_group)
        
        return {
            "message": message,
            "results": results,
            "timestamp": app_logger.get_current_date()
        }
        
    except Exception as e:
        app_logger.error("Cache clear failed", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@admin_router.post("/cache/warm-up")
async def warm_up_cache(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Pré-aquece o cache com dados essenciais.
    """
    try:
        cache_manager = get_cache_manager()
        results = await cache_manager.warm_up_cache()
        
        api_logger.log_endpoint_call("warm_up_cache", credentials.username)
        
        return {
            "message": "Cache warm-up completed",
            "results": results,
            "timestamp": app_logger.get_current_date()
        }
        
    except Exception as e:
        app_logger.error("Cache warm-up failed", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@admin_router.get("/logs/recent")
async def get_recent_logs(
    lines: int = 100,
    level: Optional[str] = None,
    credentials: HTTPBasicCredentials = Depends(verify_basic_auth)
):
    """
    Obtém logs recentes do sistema.
    
    Args:
        lines: Número de linhas para retornar (máximo 1000)
        level: Filtro por nível (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    try:
        # Limita número de linhas
        lines = min(lines, 1000)
        
        # TODO: Implementar leitura de logs
        # Por agora retorna informação básica
        log_info = {
            "message": "Log endpoint not fully implemented",
            "requested_lines": lines,
            "requested_level": level,
            "note": "Logs are available in the configured log files"
        }
        
        api_logger.log_endpoint_call("get_recent_logs", credentials.username, lines=lines, level=level)
        
        return log_info
        
    except Exception as e:
        app_logger.error("Failed to get recent logs", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@admin_router.post("/system/gc")
async def trigger_garbage_collection(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Força coleta de lixo do Python.
    Útil para liberar memória em situações específicas.
    """
    try:
        import gc
        
        # Informações antes da GC
        before = {
            "collections": gc.get_count(),
            "objects": len(gc.get_objects())
        }
        
        # Executa coleta de lixo
        collected = gc.collect()
        
        # Informações depois da GC
        after = {
            "collections": gc.get_count(),
            "objects": len(gc.get_objects())
        }
        
        api_logger.log_endpoint_call("garbage_collection", credentials.username)
        app_logger.info("Manual garbage collection triggered", collected_objects=collected)
        
        return {
            "message": "Garbage collection completed",
            "collected_objects": collected,
            "before": before,
            "after": after,
            "objects_freed": before["objects"] - after["objects"]
        }
        
    except Exception as e:
        app_logger.error("Garbage collection failed", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

@admin_router.get("/config")
async def get_system_config(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Retorna configurações do sistema (sem dados sensíveis).
    """
    try:
        config_info = {
            "api": {
                "version": api_config.VERSION,
                "title": api_config.TITLE,
                "http_timeout": api_config.HTTP_TIMEOUT,
                "rate_limit_requests": api_config.RATE_LIMIT_REQUESTS,
                "rate_limit_window": api_config.RATE_LIMIT_WINDOW
            },
            "cache": {
                "default_ttl": cache_config.DEFAULT_TTL,
                "courses_ttl": cache_config.COURSES_TTL,
                "users_ttl": cache_config.USERS_TTL,
                "g2_courses_ttl": cache_config.G2_COURSES_TTL
            },
            "environment": {
                "is_development": is_development(),
                "is_production": is_production()
            }
        }
        
        api_logger.log_endpoint_call("get_system_config", credentials.username)
        
        return config_info
        
    except Exception as e:
        app_logger.error("Failed to get system config", error=e)
        raise HTTPException(
            status_code=HTTP_STATUS["INTERNAL_ERROR"],
            detail=ERROR_MESSAGES["INTERNAL_ERROR"]
        )

# Funções auxiliares
def get_current_date():
    """Função auxiliar para obter data atual."""
    from datetime import datetime
    return datetime.now().isoformat()

def is_development():
    """Check if running in development mode."""
    from ..config import is_development
    return is_development()

def is_production():
    """Check if running in production mode.""" 
    from ..config import is_production
    return is_production()
