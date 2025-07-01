"""
Sistema de logging estruturado para a API NPI-backend.
Fornece logging consistente com contexto e métricas.
"""

import json
import sys
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional, Callable
from loguru import logger

from ..config import log_config, is_development

class StructuredLogger:
    """Logger estruturado com contexto e métricas."""
    
    def __init__(self):
        """Inicializa o logger com configurações personalizadas."""
        self._setup_logger()
    
    def _setup_logger(self):
        """Configura o logger com formato estruturado."""
        # Remove o logger padrão
        logger.remove()
        
        # Formato para desenvolvimento
        if is_development():
            format_string = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )
            logger.add(sys.stdout, format=format_string, level=log_config.LEVEL)
        else:
            # Formato JSON para produção
            def json_formatter(record):
                log_entry = {
                    "timestamp": record["time"].isoformat(),
                    "level": record["level"].name,
                    "module": record["name"],
                    "function": record["function"],
                    "line": record["line"],
                    "message": record["message"],
                }
                
                # Adiciona contexto extra se disponível
                if "context" in record["extra"]:
                    log_entry.update(record["extra"]["context"])
                    
                return json.dumps(log_entry)
            
            logger.add(
                sys.stdout,
                format=json_formatter,
                level=log_config.LEVEL,
                serialize=True
            )
            
            # Adiciona arquivo de log para produção
            logger.add(
                "logs/api_{time}.log",
                format=json_formatter,
                level=log_config.LEVEL,
                rotation=log_config.ROTATION,
                retention=log_config.RETENTION,
                serialize=True
            )
    
    def info(self, message: str, **context):
        """Log de informação com contexto."""
        logger.bind(context=context).info(message)
    
    def debug(self, message: str, **context):
        """Log de debug com contexto."""
        logger.bind(context=context).debug(message)
    
    def warning(self, message: str, **context):
        """Log de warning com contexto."""
        logger.bind(context=context).warning(message)
    
    def error(self, message: str, error: Optional[Exception] = None, **context):
        """Log de erro com contexto e stack trace."""
        if error:
            context["error_type"] = type(error).__name__
            context["error_message"] = str(error)
        logger.bind(context=context).error(message)
    
    def critical(self, message: str, error: Optional[Exception] = None, **context):
        """Log crítico com contexto."""
        if error:
            context["error_type"] = type(error).__name__ 
            context["error_message"] = str(error)
        logger.bind(context=context).critical(message)

# Instância global do logger
app_logger = StructuredLogger()

class RequestLogger:
    """Logger específico para requisições HTTP."""
    
    @staticmethod
    def log_request(
        method: str,
        path: str,
        status_code: int,
        duration: float,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        **extra_context
    ):
        """Log detalhado de requisições HTTP."""
        context = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_id": user_id,
            "client_ip": client_ip,
            **extra_context
        }
        
        level = "info"
        if status_code >= 500:
            level = "error"
        elif status_code >= 400:
            level = "warning"
        
        message = f"{method} {path} - {status_code} ({context['duration_ms']}ms)"
        
        getattr(app_logger, level)(message, **context)

class CacheLogger:
    """Logger específico para operações de cache."""
    
    @staticmethod
    def log_hit(cache_key: str, ttl: Optional[int] = None, **context):
        """Log de cache hit."""
        app_logger.debug(
            f"Cache HIT: {cache_key}",
            cache_key=cache_key,
            cache_operation="hit",
            ttl=ttl,
            **context
        )
    
    @staticmethod
    def log_miss(cache_key: str, **context):
        """Log de cache miss."""
        app_logger.debug(
            f"Cache MISS: {cache_key}",
            cache_key=cache_key,
            cache_operation="miss",
            **context
        )
    
    @staticmethod
    def log_set(cache_key: str, ttl: int, **context):
        """Log de operação de cache set."""
        app_logger.debug(
            f"Cache SET: {cache_key} (TTL: {ttl}s)",
            cache_key=cache_key,
            cache_operation="set",
            ttl=ttl,
            **context
        )
    
    @staticmethod
    def log_delete(cache_key: str, **context):
        """Log de operação de cache delete."""
        app_logger.info(
            f"Cache DELETE: {cache_key}",
            cache_key=cache_key,
            cache_operation="delete",
            **context
        )

class APILogger:
    """Logger específico para operações da API."""
    
    @staticmethod
    def log_endpoint_call(endpoint: str, user: Optional[str] = None, **context):
        """Log de chamada de endpoint."""
        app_logger.info(
            f"Endpoint called: {endpoint}",
            endpoint=endpoint,
            user=user,
            **context
        )
    
    @staticmethod
    def log_data_processing(operation: str, records_count: int, duration: float, **context):
        """Log de processamento de dados."""
        app_logger.info(
            f"Data processing: {operation} ({records_count} records, {duration:.2f}s)",
            operation=operation,
            records_count=records_count,
            duration=duration,
            **context
        )
    
    @staticmethod
    def log_external_api_call(service: str, endpoint: str, status_code: int, duration: float, **context):
        """Log de chamadas para APIs externas."""
        context.update({
            "service": service,
            "endpoint": endpoint,
            "status_code": status_code,
            "duration": duration,
            "api_type": "external"
        })
        
        level = "info"
        if status_code >= 500:
            level = "error"
        elif status_code >= 400:
            level = "warning"
        
        message = f"External API call: {service} - {status_code} ({duration:.2f}s)"
        getattr(app_logger, level)(message, **context)

def log_execution_time(operation_name: str):
    """Decorator para medir e logar tempo de execução."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                app_logger.debug(
                    f"Operation completed: {operation_name}",
                    operation=operation_name,
                    duration=duration,
                    success=True
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                app_logger.error(
                    f"Operation failed: {operation_name}",
                    operation=operation_name,
                    duration=duration,
                    success=False,
                    error=e
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                app_logger.debug(
                    f"Operation completed: {operation_name}",
                    operation=operation_name,
                    duration=duration,
                    success=True
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                app_logger.error(
                    f"Operation failed: {operation_name}",
                    operation=operation_name,
                    duration=duration,
                    success=False,
                    error=e
                )
                raise
        
        # Retorna wrapper apropriado baseado no tipo da função
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

# Instâncias dos loggers especializados
app_logger = StructuredLogger("app")
request_logger = RequestLogger()
cache_logger = CacheLogger()
api_logger = APILogger()
security_logger = StructuredLogger("security")
error_logger = StructuredLogger("error")
performance_logger = StructuredLogger("performance")
validation_logger = StructuredLogger("validation")
retry_logger = StructuredLogger("retry")

# Função de conveniência para logging rápido
def log_info(message: str, **context):
    """Função de conveniência para logging rápido."""
    app_logger.info(message, **context)

def log_error(message: str, error: Optional[Exception] = None, **context):
    """Função de conveniência para logging de erros."""
    app_logger.error(message, error=error, **context)
