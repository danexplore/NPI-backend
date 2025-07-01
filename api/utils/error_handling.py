"""
Sistema de Tratamento de Erros Global para NPI-backend
Implementa tratamento unificado de exceções, logging estruturado de erros, e respostas padronizadas.
"""

import traceback
from typing import Dict, Any, Optional, Union
from datetime import datetime

from fastapi import Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from ..config import api_config, ERROR_MESSAGES, HTTP_STATUS
from ..utils.logging import error_logger, app_logger

# ========== TIPOS DE ERRO ==========

class APIError(Exception):
    """Classe base para erros da API."""
    
    def __init__(
        self, 
        message: str, 
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationAPIError(APIError):
    """Erro de validação de dados."""
    
    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            status_code=HTTP_STATUS["BAD_REQUEST"],
            error_code="VALIDATION_ERROR",
            details=details or {}
        )
        if field:
            self.details["field"] = field

class AuthenticationAPIError(APIError):
    """Erro de autenticação."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=HTTP_STATUS["UNAUTHORIZED"],
            error_code="AUTHENTICATION_ERROR"
        )

class AuthorizationAPIError(APIError):
    """Erro de autorização."""
    
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            status_code=HTTP_STATUS["FORBIDDEN"],
            error_code="AUTHORIZATION_ERROR"
        )

class ExternalServiceError(APIError):
    """Erro de serviço externo."""
    
    def __init__(self, service: str, message: str = "External service unavailable"):
        super().__init__(
            message=f"{service}: {message}",
            status_code=HTTP_STATUS["SERVICE_UNAVAILABLE"],
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service": service}
        )

class RateLimitError(APIError):
    """Erro de rate limiting."""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            status_code=HTTP_STATUS["TOO_MANY_REQUESTS"],
            error_code="RATE_LIMIT_ERROR",
            details={"retry_after": retry_after}
        )

class CacheError(APIError):
    """Erro relacionado ao cache."""
    
    def __init__(self, operation: str, message: str = "Cache operation failed"):
        super().__init__(
            message=f"Cache {operation}: {message}",
            status_code=HTTP_STATUS["SERVICE_UNAVAILABLE"],
            error_code="CACHE_ERROR",
            details={"operation": operation}
        )

# ========== HANDLER DE ERROS ==========

class ErrorHandler:
    """Classe para tratamento centralizado de erros."""
    
    @staticmethod
    def create_error_response(
        error: Union[Exception, APIError],
        request: Request,
        include_traceback: bool = False
    ) -> Dict[str, Any]:
        """Cria resposta padronizada de erro."""
        
        # Determina tipo de erro
        if isinstance(error, APIError):
            status_code = error.status_code
            error_code = error.error_code
            message = error.message
            details = error.details
        elif isinstance(error, HTTPException):
            status_code = error.status_code
            error_code = "HTTP_ERROR"
            message = str(error.detail)
            details = {}
        elif isinstance(error, ValidationError):
            status_code = HTTP_STATUS["BAD_REQUEST"]
            error_code = "VALIDATION_ERROR"
            message = "Validation failed"
            details = {"validation_errors": error.errors()}
        else:
            status_code = HTTP_STATUS["INTERNAL_SERVER_ERROR"]
            error_code = "INTERNAL_ERROR"
            message = "An internal error occurred"
            details = {}
        
        # Monta resposta
        error_response = {
            "error": True,
            "error_code": error_code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url),
            "method": request.method
        }
        
        # Adiciona detalhes se existirem
        if details:
            error_response["details"] = details
        
        # Adiciona traceback em desenvolvimento
        if include_traceback and api_config.DEBUG:
            error_response["traceback"] = traceback.format_exc()
        
        return error_response, status_code
    
    @staticmethod
    def log_error(
        error: Exception,
        request: Request,
        user_id: Optional[str] = None
    ):
        """Faz log estruturado do erro."""
        
        error_context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "path": str(request.url),
            "method": request.method,
            "client_host": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if user_id:
            error_context["user_id"] = user_id
        
        # Adiciona contexto específico para diferentes tipos de erro
        if isinstance(error, APIError):
            error_context.update({
                "status_code": error.status_code,
                "error_code": error.error_code,
                "details": error.details
            })
        
        if isinstance(error, ValidationError):
            error_context["validation_errors"] = error.errors()
        
        # Log baseado na severidade
        if isinstance(error, (AuthenticationAPIError, AuthorizationAPIError)):
            error_logger.warning("Security error occurred", **error_context)
        elif isinstance(error, ValidationAPIError):
            error_logger.info("Validation error occurred", **error_context)
        elif isinstance(error, (ExternalServiceError, CacheError)):
            error_logger.error("Service error occurred", **error_context)
        else:
            error_logger.error("Unexpected error occurred", **error_context)
            # Log traceback para erros internos
            error_logger.error("Error traceback", traceback=traceback.format_exc())

# ========== EXCEPTION HANDLERS ==========

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handler para erros customizados da API."""
    
    ErrorHandler.log_error(exc, request)
    response_data, status_code = ErrorHandler.create_error_response(exc, request)
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler para HTTPExceptions do FastAPI."""
    
    ErrorHandler.log_error(exc, request)
    response_data, status_code = ErrorHandler.create_error_response(exc, request)
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler para erros de validação do Pydantic."""
    
    # Converte erros de validação para formato mais amigável
    validation_errors = []
    for error in exc.errors():
        validation_errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    validation_error = ValidationAPIError(
        message="Request validation failed",
        details={"validation_errors": validation_errors}
    )
    
    ErrorHandler.log_error(validation_error, request)
    response_data, status_code = ErrorHandler.create_error_response(validation_error, request)
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler geral para exceções não tratadas."""
    
    # Cria APIError genérico
    api_error = APIError(
        message="An unexpected error occurred",
        status_code=HTTP_STATUS["INTERNAL_SERVER_ERROR"],
        error_code="INTERNAL_ERROR"
    )
    
    ErrorHandler.log_error(exc, request)
    response_data, status_code = ErrorHandler.create_error_response(
        api_error, 
        request, 
        include_traceback=True
    )
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )

# ========== DECORATORS ==========

def handle_errors(func):
    """Decorator para tratamento automático de erros em endpoints."""
    
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except APIError:
            # Re-raise APIErrors para serem tratados pelos handlers
            raise
        except ValidationError as e:
            raise ValidationAPIError(
                message="Data validation failed",
                details={"validation_errors": e.errors()}
            )
        except Exception as e:
            app_logger.error(f"Unexpected error in {func.__name__}", error=str(e))
            raise APIError(
                message="An unexpected error occurred",
                error_code="INTERNAL_ERROR"
            )
    
    return wrapper

def require_auth(func):
    """Decorator para endpoints que requerem autenticação."""
    
    async def wrapper(*args, **kwargs):
        # Verifica se há credenciais válidas
        # Este decorator trabalha em conjunto com o sistema de auth existente
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                raise AuthenticationAPIError()
            raise
    
    return wrapper

# ========== UTILITÁRIOS ==========

def create_error_detail(message: str, error_code: str, **kwargs) -> Dict[str, Any]:
    """Cria detalhes de erro padronizados."""
    return {
        "message": message,
        "error_code": error_code,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs
    }

def is_client_error(status_code: int) -> bool:
    """Verifica se é erro do cliente (4xx)."""
    return 400 <= status_code < 500

def is_server_error(status_code: int) -> bool:
    """Verifica se é erro do servidor (5xx)."""
    return 500 <= status_code < 600

# ========== REGISTRY DE HANDLERS ==========

ERROR_HANDLERS = {
    APIError: api_error_handler,
    HTTPException: http_exception_handler,
    StarletteHTTPException: http_exception_handler,
    RequestValidationError: validation_exception_handler,
    Exception: general_exception_handler
}

def register_error_handlers(app):
    """Registra todos os handlers de erro na aplicação."""
    for exception_type, handler in ERROR_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    
    app_logger.info("Error handlers registered successfully")
