"""
Sistema de Retry Automático para NPI-backend
Implementa retry inteligente para operações que podem falhar temporariamente.
"""

import asyncio
import random
from typing import Callable, Any, Optional, List, Union, Dict
from datetime import datetime, timedelta
from functools import wraps
from dataclasses import dataclass
from enum import Enum

from ..utils.logging import retry_logger
from ..utils.error_handling import ExternalServiceError, CacheError

# ========== CONFIGURAÇÕES DE RETRY ==========

class RetryStrategy(Enum):
    """Estratégias de retry disponíveis."""
    
    FIXED = "fixed"           # Intervalo fixo
    EXPONENTIAL = "exponential"  # Backoff exponencial
    LINEAR = "linear"         # Incremento linear
    RANDOM = "random"         # Jitter aleatório

@dataclass
class RetryConfig:
    """Configuração para retry automático."""
    
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    backoff_factor: float = 2.0
    jitter: bool = True
    retry_on: List[type] = None
    stop_on: List[type] = None
    
    def __post_init__(self):
        if self.retry_on is None:
            self.retry_on = [
                ConnectionError,
                TimeoutError,
                ExternalServiceError,
                CacheError
            ]
        
        if self.stop_on is None:
            self.stop_on = [
                ValueError,
                TypeError,
                KeyError
            ]

# ========== RETRY MANAGER ==========

class RetryManager:
    """Gerenciador de retry com diferentes estratégias."""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "avg_attempts": 0.0
        }
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        context: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Executa função com retry automático."""
        
        context = context or func.__name__
        attempts = 0
        last_exception = None
        
        retry_logger.info(
            "Starting retry execution",
            context=context,
            max_attempts=self.config.max_attempts,
            strategy=self.config.strategy.value
        )
        
        while attempts < self.config.max_attempts:
            attempts += 1
            self.stats["total_attempts"] += 1
            
            try:
                retry_logger.debug(
                    "Executing attempt",
                    context=context,
                    attempt=attempts,
                    max_attempts=self.config.max_attempts
                )
                
                # Executa a função
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Sucesso
                if attempts > 1:
                    self.stats["successful_retries"] += 1
                    retry_logger.info(
                        "Retry successful",
                        context=context,
                        attempts_needed=attempts,
                        max_attempts=self.config.max_attempts
                    )
                
                self._update_stats(attempts)
                return result
                
            except Exception as e:
                last_exception = e
                
                # Verifica se deve parar
                if self._should_stop_retry(e):
                    retry_logger.warning(
                        "Stopping retry due to non-retryable error",
                        context=context,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    break
                
                # Verifica se deve tentar novamente
                if not self._should_retry(e):
                    retry_logger.warning(
                        "Not retrying due to error type",
                        context=context,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    break
                
                # Se não é a última tentativa, aguarda e tenta novamente
                if attempts < self.config.max_attempts:
                    delay = self._calculate_delay(attempts)
                    
                    retry_logger.warning(
                        "Attempt failed, retrying",
                        context=context,
                        attempt=attempts,
                        max_attempts=self.config.max_attempts,
                        error=str(e),
                        retry_delay=delay
                    )
                    
                    await asyncio.sleep(delay)
                else:
                    retry_logger.error(
                        "All retry attempts failed",
                        context=context,
                        total_attempts=attempts,
                        final_error=str(e)
                    )
        
        # Todas as tentativas falharam
        self.stats["failed_retries"] += 1
        self._update_stats(attempts)
        
        # Re-raise a última exceção
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError(f"Retry failed after {attempts} attempts")
    
    def _should_retry(self, exception: Exception) -> bool:
        """Verifica se deve tentar novamente baseado no tipo de exceção."""
        return any(isinstance(exception, exc_type) for exc_type in self.config.retry_on)
    
    def _should_stop_retry(self, exception: Exception) -> bool:
        """Verifica se deve parar de tentar baseado no tipo de exceção."""
        return any(isinstance(exception, exc_type) for exc_type in self.config.stop_on)
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calcula delay baseado na estratégia configurada."""
        
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
            
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.backoff_factor ** (attempt - 1))
            
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay * attempt
            
        elif self.config.strategy == RetryStrategy.RANDOM:
            delay = random.uniform(self.config.base_delay, self.config.max_delay)
            
        else:
            delay = self.config.base_delay
        
        # Aplica limite máximo
        delay = min(delay, self.config.max_delay)
        
        # Adiciona jitter se configurado
        if self.config.jitter:
            jitter_factor = random.uniform(0.8, 1.2)
            delay *= jitter_factor
        
        return delay
    
    def _update_stats(self, attempts: int):
        """Atualiza estatísticas de retry."""
        total_ops = self.stats["successful_retries"] + self.stats["failed_retries"]
        if total_ops > 0:
            self.stats["avg_attempts"] = self.stats["total_attempts"] / total_ops
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas de retry."""
        return self.stats.copy()

# ========== CONFIGURAÇÕES PRÉ-DEFINIDAS ==========

# Configurações específicas para diferentes tipos de operação
RETRY_CONFIGS = {
    "external_api": RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        strategy=RetryStrategy.EXPONENTIAL,
        backoff_factor=2.0,
        jitter=True,
        retry_on=[ConnectionError, TimeoutError, ExternalServiceError]
    ),
    
    "cache_operation": RetryConfig(
        max_attempts=2,
        base_delay=0.5,
        max_delay=5.0,
        strategy=RetryStrategy.FIXED,
        jitter=False,
        retry_on=[CacheError, ConnectionError]
    ),
    
    "database_operation": RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=10.0,
        strategy=RetryStrategy.LINEAR,
        jitter=True,
        retry_on=[ConnectionError, TimeoutError]
    ),
    
    "file_operation": RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.FIXED,
        jitter=False,
        retry_on=[OSError, IOError]
    )
}

# ========== MANAGERS GLOBAIS ==========

_retry_managers = {}

def get_retry_manager(config_name: str = "external_api") -> RetryManager:
    """Obtém manager de retry baseado na configuração."""
    if config_name not in _retry_managers:
        config = RETRY_CONFIGS.get(config_name, RETRY_CONFIGS["external_api"])
        _retry_managers[config_name] = RetryManager(config)
    
    return _retry_managers[config_name]

# ========== DECORATORS ==========

def retry(
    config_name: str = "external_api",
    context: Optional[str] = None,
    custom_config: Optional[RetryConfig] = None
):
    """Decorator para retry automático."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if custom_config:
                manager = RetryManager(custom_config)
            else:
                manager = get_retry_manager(config_name)
            
            return await manager.execute_with_retry(
                func, *args, context=context, **kwargs
            )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if custom_config:
                manager = RetryManager(custom_config)
            else:
                manager = get_retry_manager(config_name)
            
            return asyncio.run(manager.execute_with_retry(
                func, *args, context=context, **kwargs
            ))
        
        # Retorna wrapper apropriado baseado no tipo da função
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def retry_external_api(func: Callable) -> Callable:
    """Decorator específico para APIs externas."""
    return retry("external_api", context=f"external_api_{func.__name__}")(func)

def retry_cache_operation(func: Callable) -> Callable:
    """Decorator específico para operações de cache."""
    return retry("cache_operation", context=f"cache_{func.__name__}")(func)

def retry_database_operation(func: Callable) -> Callable:
    """Decorator específico para operações de banco."""
    return retry("database_operation", context=f"db_{func.__name__}")(func)

# ========== CIRCUIT BREAKER ==========

class CircuitState(Enum):
    """Estados do circuit breaker."""
    CLOSED = "closed"       # Funcionando normalmente
    OPEN = "open"          # Falhou muito, rejeitando requests
    HALF_OPEN = "half_open" # Testando se voltou a funcionar

@dataclass
class CircuitBreakerConfig:
    """Configuração do circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: type = Exception

class CircuitBreaker:
    """Circuit breaker para proteção contra falhas em cascata."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "circuit_opened_count": 0
        }
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Executa função com circuit breaker."""
        
        self.stats["total_requests"] += 1
        
        # Verifica estado atual
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                retry_logger.info("Circuit breaker moved to HALF_OPEN state")
            else:
                retry_logger.warning("Circuit breaker is OPEN, rejecting request")
                raise ExternalServiceError("Circuit breaker", "Service temporarily unavailable")
        
        try:
            # Executa função
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Sucesso - reset contador
            self._on_success()
            return result
            
        except Exception as e:
            if isinstance(e, self.config.expected_exception):
                self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Verifica se deve tentar resetar o circuit breaker."""
        if self.last_failure_time is None:
            return True
        
        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.recovery_timeout
    
    def _on_success(self):
        """Trata sucesso da operação."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.stats["successful_requests"] += 1
        
        if self.state == CircuitState.HALF_OPEN:
            retry_logger.info("Circuit breaker reset to CLOSED state")
    
    def _on_failure(self):
        """Trata falha da operação."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.stats["failed_requests"] += 1
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.stats["circuit_opened_count"] += 1
            retry_logger.warning(
                "Circuit breaker opened",
                failure_count=self.failure_count,
                threshold=self.config.failure_threshold
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do circuit breaker."""
        return {
            **self.stats,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
        }
