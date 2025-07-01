"""
Middleware de Segurança Avançado para NPI-backend
Implementa validações de segurança, rate limiting, e proteções contra ataques comuns.
"""

import time
import hashlib
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional, Set
from datetime import datetime, timedelta

from fastapi import Request, Response, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import security_config
from ..utils.logging import security_logger

# ========== RATE LIMITING ==========

class RateLimiter:
    """Sistema de rate limiting avançado com diferentes estratégias."""
    
    def __init__(self):
        self.requests: Dict[str, deque] = defaultdict(lambda: deque())
        self.blocked_ips: Dict[str, datetime] = {}
        self.suspicious_ips: Set[str] = set()
    
    def is_blocked(self, client_ip: str) -> bool:
        """Verifica se IP está bloqueado."""
        if client_ip in self.blocked_ips:
            if datetime.now() < self.blocked_ips[client_ip]:
                return True
            else:
                # Remove IP da lista de bloqueados se expirou
                del self.blocked_ips[client_ip]
        return False
    
    def check_rate_limit(self, client_ip: str, endpoint: str) -> Tuple[bool, int]:
        """
        Verifica rate limit para um IP e endpoint.
        Retorna (is_allowed, remaining_requests).
        """
        if self.is_blocked(client_ip):
            return False, 0
        
        now = time.time()
        key = f"{client_ip}:{endpoint}"
        
        # Remove requests antigas
        while self.requests[key] and self.requests[key][0] < now - security_config.RATE_LIMIT_WINDOW:
            self.requests[key].popleft()
        
        # Verifica limite
        if len(self.requests[key]) >= security_config.RATE_LIMIT_REQUESTS:
            self._handle_rate_limit_exceeded(client_ip, endpoint)
            return False, 0
        
        # Adiciona request atual
        self.requests[key].append(now)
        remaining = security_config.RATE_LIMIT_REQUESTS - len(self.requests[key])
        
        return True, remaining
    
    def _handle_rate_limit_exceeded(self, client_ip: str, endpoint: str):
        """Trata quando rate limit é excedido."""
        self.suspicious_ips.add(client_ip)
        
        # Bloqueia IP temporariamente se muito suspeito
        if self._is_highly_suspicious(client_ip):
            block_until = datetime.now() + timedelta(minutes=security_config.BLOCK_DURATION_MINUTES)
            self.blocked_ips[client_ip] = block_until
            
            security_logger.warning(
                "IP blocked for suspicious activity",
                client_ip=client_ip,
                endpoint=endpoint,
                block_until=block_until.isoformat()
            )
    
    def _is_highly_suspicious(self, client_ip: str) -> bool:
        """Determina se IP é altamente suspeito."""
        # Contabiliza requests em endpoints diferentes
        total_requests = sum(
            len(deque_) for key, deque_ in self.requests.items() 
            if key.startswith(f"{client_ip}:")
        )
        
        return total_requests > security_config.SUSPICIOUS_REQUEST_THRESHOLD

# ========== MIDDLEWARE DE SEGURANÇA ==========

class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware de segurança com múltiplas proteções."""
    
    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }
    
    async def dispatch(self, request: Request, call_next):
        """Processa request com verificações de segurança."""
        start_time = time.time()
        
        # Obtém IP do cliente
        client_ip = self._get_client_ip(request)
        endpoint = request.url.path
        
        # Log da request
        security_logger.info(
            "Security check started",
            client_ip=client_ip,
            endpoint=endpoint,
            method=request.method,
            user_agent=request.headers.get("user-agent", "unknown")
        )
        
        # Verifica rate limiting
        is_allowed, remaining = self.rate_limiter.check_rate_limit(client_ip, endpoint)
        if not is_allowed:
            security_logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                endpoint=endpoint
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": security_config.RATE_LIMIT_WINDOW
                },
                headers={"Retry-After": str(security_config.RATE_LIMIT_WINDOW)}
            )
        
        # Verifica headers suspeitos
        if self._has_suspicious_headers(request):
            security_logger.warning(
                "Suspicious headers detected",
                client_ip=client_ip,
                endpoint=endpoint,
                headers=dict(request.headers)
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Bad request"}
            )
        
        # Verifica payload size
        if self._payload_too_large(request):
            security_logger.warning(
                "Payload too large",
                client_ip=client_ip,
                endpoint=endpoint,
                content_length=request.headers.get("content-length", "unknown")
            )
            return JSONResponse(
                status_code=413,
                content={"detail": "Payload too large"}
            )
        
        try:
            # Processa request
            response = await call_next(request)
            
            # Adiciona headers de segurança
            for header, value in self.security_headers.items():
                response.headers[header] = value
            
            # Adiciona headers de rate limiting
            response.headers["X-RateLimit-Limit"] = str(security_config.RATE_LIMIT_REQUESTS)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(start_time + security_config.RATE_LIMIT_WINDOW))
            
            # Log sucesso
            process_time = time.time() - start_time
            security_logger.info(
                "Security check completed",
                client_ip=client_ip,
                endpoint=endpoint,
                status_code=response.status_code,
                process_time=round(process_time, 3)
            )
            
            return response
            
        except Exception as e:
            security_logger.error(
                "Security middleware error",
                client_ip=client_ip,
                endpoint=endpoint,
                error=str(e)
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Obtém IP real do cliente considerando proxies."""
        # Verifica headers de proxy
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # IP direto
        return request.client.host if request.client else "unknown"
    
    def _has_suspicious_headers(self, request: Request) -> bool:
        """Verifica se request tem headers suspeitos."""
        suspicious_patterns = [
            "sqlmap", "nikto", "nmap", "masscan", "zap",
            "burp", "wget", "curl/7", "python-requests",
            "bot", "crawler", "spider"
        ]
        
        user_agent = request.headers.get("user-agent", "").lower()
        return any(pattern in user_agent for pattern in suspicious_patterns)
    
    def _payload_too_large(self, request: Request) -> bool:
        """Verifica se payload é muito grande."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                return size > security_config.MAX_PAYLOAD_SIZE
            except ValueError:
                return False
        return False

# ========== VALIDADOR DE INPUT ==========

class InputValidator:
    """Validador de entrada robusto para prevenir ataques."""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Valida formato de email."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """Valida força da senha."""
        if len(password) < security_config.MIN_PASSWORD_LENGTH:
            return False, f"Password must be at least {security_config.MIN_PASSWORD_LENGTH} characters"
        
        if len(password) > security_config.MAX_PASSWORD_LENGTH:
            return False, f"Password must be at most {security_config.MAX_PASSWORD_LENGTH} characters"
        
        # Verifica caracteres especiais se requerido
        if security_config.REQUIRE_SPECIAL_CHARS:
            import re
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                return False, "Password must contain at least one special character"
        
        return True, "Password is valid"
    
    @staticmethod
    def sanitize_input(input_str: str) -> str:
        """Sanitiza entrada para prevenir XSS e injection."""
        if not isinstance(input_str, str):
            return str(input_str)
        
        # Remove caracteres perigosos
        dangerous_chars = ['<', '>', '"', "'", '&', 'script', 'javascript', 'onload', 'onerror']
        sanitized = input_str
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()
    
    @staticmethod
    def validate_file_upload(filename: str, content_type: str) -> Tuple[bool, str]:
        """Valida uploads de arquivo."""
        allowed_extensions = {'.xlsx', '.xls', '.csv', '.pdf', '.png', '.jpg', '.jpeg'}
        allowed_mime_types = {
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'text/csv',
            'application/pdf',
            'image/png',
            'image/jpeg'
        }
        
        # Verifica extensão
        import os
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            return False, f"File extension {ext} not allowed"
        
        # Verifica MIME type
        if content_type not in allowed_mime_types:
            return False, f"Content type {content_type} not allowed"
        
        return True, "File is valid"

# ========== FUNÇÕES AUXILIARES ==========

def get_rate_limiter() -> RateLimiter:
    """Obtém instância global do rate limiter."""
    if not hasattr(get_rate_limiter, '_instance'):
        get_rate_limiter._instance = RateLimiter()
    return get_rate_limiter._instance

def validate_input(validator_func):
    """Decorator para validação de entrada."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Aplica validação específica
            validation_result = validator_func(*args, **kwargs)
            if not validation_result[0]:
                raise HTTPException(status_code=400, detail=validation_result[1])
            return await func(*args, **kwargs)
        return wrapper
    return decorator
