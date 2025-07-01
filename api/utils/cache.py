"""
Sistema de cache otimizado com Redis.
Inclui funcionalidades avançadas como TTL dinâmico, invalidação inteligente e métricas.
"""

import json
import time
import hashlib
from typing import Any, Dict, Optional, List, Union, Callable
from functools import wraps
from datetime import datetime, timedelta

from upstash_redis import Redis
from ..config import cache_config, CACHE_KEYS
from ..utils.logging import cache_logger, app_logger, log_execution_time

class AdvancedCache:
    """Sistema de cache avançado com recursos de observabilidade."""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.hit_count = 0
        self.miss_count = 0
        self.error_count = 0
        
    def _generate_cache_key(self, base_key: str, **params) -> str:
        """Gera chave de cache com base nos parâmetros."""
        if not params:
            return base_key
        
        # Cria hash dos parâmetros para chave única
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"{base_key}:{params_hash}"
    
    async def get(self, key: str, **params) -> Optional[Any]:
        """Obtém valor do cache com logging."""
        cache_key = self._generate_cache_key(key, **params)
        
        try:
            start_time = time.time()
            cached_data = self.redis.get(cache_key)
            duration = time.time() - start_time
            
            if cached_data is not None:
                self.hit_count += 1
                cache_logger.log_hit(cache_key, duration=duration)
                
                # Tenta decodificar JSON
                try:
                    return json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                except json.JSONDecodeError:
                    return cached_data
            else:
                self.miss_count += 1
                cache_logger.log_miss(cache_key, duration=duration)
                return None
                
        except Exception as e:
            self.error_count += 1
            app_logger.error(f"Cache get error for key: {cache_key}", error=e)
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        **params
    ) -> bool:
        """Define valor no cache com TTL."""
        cache_key = self._generate_cache_key(key, **params)
        ttl = ttl or cache_config.DEFAULT_TTL
        
        try:
            start_time = time.time()
            
            # Serializa valor se necessário
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, ensure_ascii=False)
            else:
                serialized_value = value
            
            # Define no Redis
            result = self.redis.set(cache_key, serialized_value, ex=ttl)
            duration = time.time() - start_time
            
            cache_logger.log_set(cache_key, ttl, duration=duration)
            return bool(result)
            
        except Exception as e:
            self.error_count += 1
            app_logger.error(f"Cache set error for key: {cache_key}", error=e)
            return False
    
    async def delete(self, key: str, **params) -> bool:
        """Remove valor do cache."""
        cache_key = self._generate_cache_key(key, **params)
        
        try:
            result = self.redis.delete(cache_key)
            cache_logger.log_delete(cache_key)
            return bool(result)
        except Exception as e:
            self.error_count += 1
            app_logger.error(f"Cache delete error for key: {cache_key}", error=e)
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Remove múltiplas chaves baseadas em padrão."""
        try:
            # Busca chaves que correspondem ao padrão
            keys = self.redis.keys(pattern)
            if keys:
                deleted = self.redis.delete(*keys)
                cache_logger.log_delete(f"pattern:{pattern}", deleted_count=len(keys))
                return deleted
            return 0
        except Exception as e:
            self.error_count += 1
            app_logger.error(f"Cache delete pattern error: {pattern}", error=e)
            return 0
    
    async def exists(self, key: str, **params) -> bool:
        """Verifica se chave existe no cache."""
        cache_key = self._generate_cache_key(key, **params)
        try:
            return bool(self.redis.exists(cache_key))
        except Exception as e:
            app_logger.error(f"Cache exists error for key: {cache_key}", error=e)
            return False
    
    async def get_ttl(self, key: str, **params) -> Optional[int]:
        """Obtém TTL restante de uma chave."""
        cache_key = self._generate_cache_key(key, **params)
        try:
            ttl = self.redis.ttl(cache_key)
            return ttl if ttl > 0 else None
        except Exception as e:
            app_logger.error(f"Cache TTL error for key: {cache_key}", error=e)
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self.hit_count,
            "misses": self.miss_count,
            "errors": self.error_count,
            "total_requests": total_requests,
            "hit_rate": round(hit_rate, 2),
            "error_rate": round((self.error_count / total_requests * 100) if total_requests > 0 else 0, 2)
        }
    
    async def flush_all(self) -> bool:
        """Limpa todo o cache (usar com cuidado)."""
        try:
            result = self.redis.flushdb()
            app_logger.warning("Cache flush_all executed")
            return bool(result)
        except Exception as e:
            app_logger.error("Cache flush_all error", error=e)
            return False

def cache_result(
    cache_key: str,
    ttl: Optional[int] = None,
    cache_condition: Optional[Callable] = None
):
    """Decorator para cache automático de resultados de funções."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gera chave baseada em argumentos
            key_params = {
                'args': str(args),
                'kwargs': str(sorted(kwargs.items()))
            }
            
            # Verifica condição de cache
            if cache_condition and not cache_condition(*args, **kwargs):
                return await func(*args, **kwargs)
            
            # Tenta obter do cache
            cached_result = await advanced_cache.get(cache_key, **key_params)
            if cached_result is not None:
                return cached_result
            
            # Executa função e armazena resultado
            result = await func(*args, **kwargs)
            
            # Só faz cache se resultado não for None
            if result is not None:
                await advanced_cache.set(cache_key, result, ttl, **key_params)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Para funções síncronas, executamos de forma assíncrona internamente
            import asyncio
            
            async def async_exec():
                key_params = {
                    'args': str(args),
                    'kwargs': str(sorted(kwargs.items()))
                }
                
                if cache_condition and not cache_condition(*args, **kwargs):
                    return func(*args, **kwargs)
                
                cached_result = await advanced_cache.get(cache_key, **key_params)
                if cached_result is not None:
                    return cached_result
                
                result = func(*args, **kwargs)
                
                if result is not None:
                    await advanced_cache.set(cache_key, result, ttl, **key_params)
                
                return result
            
            return asyncio.run(async_exec())
        
        # Retorna wrapper apropriado
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class CacheManager:
    """Gerenciador de cache com operações de alto nível."""
    
    def __init__(self, cache: AdvancedCache):
        self.cache = cache
    
    async def refresh_cache_group(self, group: str) -> Dict[str, bool]:
        """Atualiza um grupo de cache relacionado."""
        results = {}
        
        if group == "courses":
            # Remove caches relacionados a cursos
            patterns = [
                "courses_data*",
                "ymed_courses_data*",
                "home_data*"
            ]
            for pattern in patterns:
                deleted_count = await self.cache.delete_pattern(pattern)
                results[pattern] = deleted_count > 0
        
        elif group == "users":
            # Remove caches relacionados a usuários
            deleted_count = await self.cache.delete_pattern("users_data*")
            results["users_data"] = deleted_count > 0
        
        elif group == "g2":
            # Remove caches relacionados ao G2
            patterns = [
                "cursos_g2_data*",
                "cursos_search_data*",
                "cursos_dataframe*"
            ]
            for pattern in patterns:
                deleted_count = await self.cache.delete_pattern(pattern)
                results[pattern] = deleted_count > 0
        
        return results
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Obtém informações detalhadas do cache."""
        info = {
            "stats": self.cache.get_stats(),
            "keys_info": {}
        }
        
        # Verifica informações de chaves principais
        for key_name, cache_key in CACHE_KEYS.items():
            exists = await self.cache.exists(cache_key)
            ttl = await self.cache.get_ttl(cache_key) if exists else None
            
            info["keys_info"][key_name] = {
                "cache_key": cache_key,
                "exists": exists,
                "ttl_seconds": ttl,
                "expires_at": (datetime.now() + timedelta(seconds=ttl)).isoformat() if ttl else None
            }
        
        return info
    
    async def warm_up_cache(self) -> Dict[str, Any]:
        """Pré-aquece o cache com dados essenciais."""
        results = {}
        
        try:
            # Importa funções necessárias
            from ..scripts.courses import get_courses_unyleya, get_courses_ymed, get_home_data
            from ..scripts.login import fetch_users_from_pipefy
            from ..scripts.g2_cursos import get_g2_formatted_dataframe, get_search_formatted_dataframe
            
            # Aquece cache de usuários
            try:
                users_data = await fetch_users_from_pipefy()
                await self.cache.set(CACHE_KEYS["users"], users_data, cache_config.USERS_TTL)
                results["users"] = "success"
            except Exception as e:
                results["users"] = f"error: {str(e)}"
            
            # Aquece cache de cursos
            try:
                courses_data = await get_courses_unyleya()
                await self.cache.set(CACHE_KEYS["courses_unyleya"], courses_data, cache_config.COURSES_TTL)
                results["courses_unyleya"] = "success"
            except Exception as e:
                results["courses_unyleya"] = f"error: {str(e)}"
            
            # Aquece cache de cursos YMED
            try:
                ymed_courses = await get_courses_ymed()
                await self.cache.set(CACHE_KEYS["courses_ymed"], ymed_courses, cache_config.COURSES_TTL)
                results["courses_ymed"] = "success"
            except Exception as e:
                results["courses_ymed"] = f"error: {str(e)}"
            
            # Aquece cache de dados home
            try:
                home_data = await get_home_data()
                await self.cache.set(CACHE_KEYS["home_data"], home_data, cache_config.DEFAULT_TTL)
                results["home_data"] = "success"
            except Exception as e:
                results["home_data"] = f"error: {str(e)}"
            
            # Aquece cache G2
            try:
                g2_data = await get_g2_formatted_dataframe()
                await self.cache.set(CACHE_KEYS["g2_courses"], g2_data.to_dict('records'), cache_config.G2_COURSES_TTL)
                results["g2_courses"] = "success"
            except Exception as e:
                results["g2_courses"] = f"error: {str(e)}"
            
        except Exception as e:
            app_logger.error("Cache warm-up error", error=e)
            results["global_error"] = str(e)
        
        return results

# Instância global do cache avançado (será inicializada no main.py)
advanced_cache: Optional[AdvancedCache] = None
cache_manager: Optional[CacheManager] = None

def init_cache(redis_client: Redis):
    """Inicializa o sistema de cache."""
    global advanced_cache, cache_manager
    advanced_cache = AdvancedCache(redis_client)
    cache_manager = CacheManager(advanced_cache)
    app_logger.info("Advanced cache system initialized")

def get_cache() -> AdvancedCache:
    """Obtém instância do cache."""
    if advanced_cache is None:
        raise RuntimeError("Cache not initialized. Call init_cache() first.")
    return advanced_cache

def get_cache_manager() -> CacheManager:
    """Obtém instância do gerenciador de cache."""
    if cache_manager is None:
        raise RuntimeError("Cache manager not initialized. Call init_cache() first.")
    return cache_manager
