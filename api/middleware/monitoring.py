"""
Middleware para monitoramento de performance, métricas e observabilidade.
Inclui logging de requisições, rate limiting e health checks.
"""

import time
import asyncio
from typing import Dict, Optional, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import HTTPException, status

from ..utils.logging import request_logger, app_logger
from ..config import api_config, HTTP_STATUS, ERROR_MESSAGES

class MetricsCollector:
    """Coletor de métricas em tempo real."""
    
    def __init__(self):
        self.request_count = defaultdict(int)
        self.response_times = defaultdict(list)
        self.error_count = defaultdict(int)
        self.endpoint_stats = defaultdict(lambda: {
            'count': 0,
            'avg_response_time': 0,
            'error_rate': 0,
            'last_request': None
        })
        self.start_time = datetime.now()
        
        # Rate limiting
        self.request_history = defaultdict(lambda: deque(maxlen=100))
        
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        response_time: float,
        user_id: Optional[str] = None
    ):
        """Registra métricas de uma requisição."""
        endpoint = f"{method} {path}"
        
        # Contadores básicos
        self.request_count[endpoint] += 1
        self.response_times[endpoint].append(response_time)
        
        # Mantém apenas os últimos 100 tempos de resposta
        if len(self.response_times[endpoint]) > 100:
            self.response_times[endpoint] = self.response_times[endpoint][-100:]
        
        # Erros
        if status_code >= 400:
            self.error_count[endpoint] += 1
        
        # Estatísticas do endpoint
        stats = self.endpoint_stats[endpoint]
        stats['count'] += 1
        stats['last_request'] = datetime.now()
        
        # Calcula média de tempo de resposta
        if self.response_times[endpoint]:
            stats['avg_response_time'] = sum(self.response_times[endpoint]) / len(self.response_times[endpoint])
        
        # Calcula taxa de erro
        if stats['count'] > 0:
            stats['error_rate'] = (self.error_count[endpoint] / stats['count']) * 100
        
        # Rate limiting tracking
        if user_id:
            self.request_history[user_id].append(datetime.now())
    
    def check_rate_limit(self, user_id: str) -> bool:
        """Verifica se o usuário excedeu o rate limit."""
        now = datetime.now()
        window_start = now - timedelta(seconds=api_config.RATE_LIMIT_WINDOW)
        
        # Remove requisições antigas
        user_requests = self.request_history[user_id]
        while user_requests and user_requests[0] < window_start:
            user_requests.popleft()
        
        return len(user_requests) >= api_config.RATE_LIMIT_REQUESTS
    
    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas coletadas."""
        uptime = datetime.now() - self.start_time
        
        # Top endpoints por quantidade de requisições
        top_endpoints = sorted(
            self.endpoint_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:10]
        
        # Endpoints mais lentos
        slow_endpoints = sorted(
            [(k, v) for k, v in self.endpoint_stats.items() if v['avg_response_time'] > 0],
            key=lambda x: x[1]['avg_response_time'],
            reverse=True
        )[:5]
        
        # Endpoints com mais erros
        error_endpoints = sorted(
            [(k, v) for k, v in self.endpoint_stats.items() if v['error_rate'] > 0],
            key=lambda x: x[1]['error_rate'],
            reverse=True
        )[:5]
        
        total_requests = sum(self.request_count.values())
        total_errors = sum(self.error_count.values())
        
        return {
            "system": {
                "uptime_seconds": int(uptime.total_seconds()),
                "start_time": self.start_time.isoformat(),
                "version": api_config.VERSION
            },
            "requests": {
                "total": total_requests,
                "total_errors": total_errors,
                "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0
            },
            "performance": {
                "top_endpoints": [
                    {
                        "endpoint": endpoint,
                        "count": stats['count'],
                        "avg_response_time": round(stats['avg_response_time'], 3),
                        "error_rate": round(stats['error_rate'], 2)
                    }
                    for endpoint, stats in top_endpoints
                ],
                "slowest_endpoints": [
                    {
                        "endpoint": endpoint,
                        "avg_response_time": round(stats['avg_response_time'], 3),
                        "count": stats['count']
                    }
                    for endpoint, stats in slow_endpoints
                ],
                "highest_error_rate": [
                    {
                        "endpoint": endpoint,
                        "error_rate": round(stats['error_rate'], 2),
                        "count": stats['count']
                    }
                    for endpoint, stats in error_endpoints
                ]
            }
        }

# Instância global do coletor de métricas
metrics_collector = MetricsCollector()

class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware para monitoramento de performance e logging."""
    
    async def dispatch(self, request: Request, call_next):
        """Processa requisições com monitoramento."""
        start_time = time.time()
        
        # Extrai informações da requisição
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Rate limiting básico (se configurado)
        user_id = None
        if hasattr(request.state, 'user'):
            user_id = getattr(request.state.user, 'id', None)
        
        # Verifica rate limit
        if user_id and metrics_collector.check_rate_limit(user_id):
            app_logger.warning(
                "Rate limit exceeded",
                user_id=user_id,
                client_ip=client_ip,
                path=path
            )
            return JSONResponse(
                status_code=HTTP_STATUS["RATE_LIMITED"],
                content={"error": ERROR_MESSAGES["RATE_LIMITED"]},
                headers={"Retry-After": str(api_config.RATE_LIMIT_WINDOW)}
            )
        
        # Processa requisição
        try:
            response = await call_next(request)
            status_code = response.status_code
            
        except Exception as e:
            # Log do erro interno
            app_logger.error(
                "Internal server error during request processing",
                error=e,
                method=method,
                path=path,
                client_ip=client_ip
            )
            
            response = JSONResponse(
                status_code=HTTP_STATUS["INTERNAL_ERROR"],
                content={"error": ERROR_MESSAGES["INTERNAL_ERROR"]}
            )
            status_code = response.status_code
        
        # Calcula tempo de resposta
        duration = time.time() - start_time
        
        # Registra métricas
        metrics_collector.record_request(method, path, status_code, duration, user_id)
        
        # Log da requisição
        request_logger.log_request(
            method=method,
            path=path,
            status_code=status_code,
            duration=duration,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        # Adiciona headers de performance
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        response.headers["X-Request-ID"] = str(id(request))
        
        return response

class HealthCheckMiddleware:
    """Utilitários para health checks e monitoramento de saúde."""
    
    @staticmethod
    async def check_redis_health() -> Dict[str, Any]:
        """Verifica saúde do Redis."""
        try:
            from ..main import redis  # Import local para evitar circular
            
            start_time = time.time()
            await redis.ping()
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "response_time": round(response_time * 1000, 2),
                "message": "Redis connection successful"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "message": "Redis connection failed"
            }
    
    @staticmethod
    async def check_external_apis_health() -> Dict[str, Any]:
        """Verifica saúde de APIs externas."""
        checks = {}
        
        # Verifica G2 API (exemplo)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                start_time = time.time()
                response = await client.get("https://g2s.unyleya.com.br/", follow_redirects=True)
                response_time = time.time() - start_time
                
                checks["g2_api"] = {
                    "status": "healthy" if response.status_code < 500 else "degraded",
                    "status_code": response.status_code,
                    "response_time": round(response_time * 1000, 2)
                }
        except Exception as e:
            checks["g2_api"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        return checks
    
    @staticmethod
    async def get_full_health_check() -> Dict[str, Any]:
        """Executa verificação completa de saúde."""
        redis_health = await HealthCheckMiddleware.check_redis_health()
        external_apis = await HealthCheckMiddleware.check_external_apis_health()
        
        # Determina status geral
        overall_status = "healthy"
        if redis_health["status"] == "unhealthy":
            overall_status = "unhealthy"
        elif any(api["status"] == "unhealthy" for api in external_apis.values()):
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "version": api_config.VERSION,
            "dependencies": {
                "redis": redis_health,
                "external_apis": external_apis
            },
            "metrics": metrics_collector.get_metrics()
        }

# Instância do health check
health_checker = HealthCheckMiddleware()

def get_metrics() -> Dict[str, Any]:
    """Função de conveniência para obter métricas."""
    return metrics_collector.get_metrics()

async def get_health_status() -> Dict[str, Any]:
    """Função de conveniência para obter status de saúde."""
    return await health_checker.get_full_health_check()
