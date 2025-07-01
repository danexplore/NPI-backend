"""
API Principal - NPI Backend v2.0
Sistema completo de gerenciamento de cursos com monitoramento avançado.
"""

import os
import secrets
import warnings
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from upstash_redis import Redis
from dotenv import load_dotenv

# Imports locais
from .config import (
    api_config, cache_config, security_config, compression_config, monitoring_config,
    get_basic_auth_users, get_allowed_origins, 
    FIELD_ORDERS, CACHE_KEYS, ERROR_MESSAGES, HTTP_STATUS,
    is_development
)
from .utils.logging import app_logger, api_logger, log_execution_time
from .utils.cache import init_cache, get_cache, cache_result
from .utils.error_handling import register_error_handlers, handle_errors, require_auth
from .utils.retry import retry_external_api, retry_cache_operation
from .utils.compression import CompressionMiddleware, get_compressor
from .utils.validation import ValidatedBaseModel, validate_input, EmailValidator
from .middleware.monitoring import PerformanceMiddleware, get_metrics, get_health_status
from .middleware.security import SecurityMiddleware, InputValidator
from .routers.monitoring import monitoring_router, admin_router
from .lib.models import *
from .scripts.courses import *
from .scripts.login import *
from .scripts.g2_cursos import *

# ========== CONFIGURAÇÃO INICIAL ==========

# Suprime warnings do Pydantic
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Carrega variáveis de ambiente em desenvolvimento
if is_development():
    load_dotenv()

# Configuração de autenticação
USERS = get_basic_auth_users()
security = HTTPBasic()

# ========== LIFECYCLE MANAGEMENT ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    app_logger.info("Starting NPI Backend API", version=api_config.VERSION)
    
    try:
        # Inicializa Redis
        redis = Redis.from_env()
        app.state.redis = redis
        
        # Inicializa sistema de cache
        init_cache(redis)
        app_logger.info("Cache system initialized")
        
        # Inicializa usuários do Pipefy
        global users
        users = await fetch_users_from_pipefy()
        if not users:
            app_logger.error("Failed to fetch users from Pipefy")
            raise HTTPException(
                status_code=HTTP_STATUS["SERVICE_UNAVAILABLE"],
                detail="Erro ao buscar usuários do Pipefy"
            )
        app_logger.info(f"Loaded {len(users)} users from Pipefy")
        
        # Pré-aquece cache em produção
        if not is_development():
            try:
                from .utils.cache import get_cache_manager
                cache_manager = get_cache_manager()
                warm_results = await cache_manager.warm_up_cache()
                app_logger.info("Cache warm-up completed", results=warm_results)
            except Exception as e:
                app_logger.warning("Cache warm-up failed", error=e)
        
        app_logger.info("API startup completed successfully")
        yield
        
    except Exception as e:
        app_logger.critical("Failed to start API", error=e)
        raise
    finally:
        app_logger.info("API shutdown initiated")
        # Cleanup se necessário
        app_logger.info("API shutdown completed")

# ========== CONFIGURAÇÃO DA APP ==========

app = FastAPI(
    title=api_config.TITLE,
    description=api_config.DESCRIPTION,
    version=api_config.VERSION,
    docs_url=api_config.DOCS_URL,
    redoc_url=api_config.REDOC_URL,
    lifespan=lifespan
)

# ========== REGISTRO DE ERROR HANDLERS ==========

register_error_handlers(app)

# ========== MIDDLEWARES ==========

# Segurança (primeiro para processar antes dos outros)
if security_config.ENABLE_SECURITY_HEADERS:
    app.add_middleware(SecurityMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compressão (antes do performance para medir corretamente)
if compression_config.ENABLE_GZIP or compression_config.ENABLE_BROTLI:
    app.add_middleware(CompressionMiddleware)

# Performance monitoring (último para capturar tudo)
app.add_middleware(PerformanceMiddleware)

# ========== ROUTERS ==========

# Inclui routers de monitoramento
app.include_router(monitoring_router)
app.include_router(admin_router)

# ========== FUNÇÕES AUXILIARES ==========

def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifica autenticação básica."""
    password = USERS.get(credentials.username)
    if not password or not secrets.compare_digest(credentials.password, password):
        app_logger.warning("Authentication failed", username=credentials.username)
        raise HTTPException(
            status_code=HTTP_STATUS["UNAUTHORIZED"],
            detail=ERROR_MESSAGES["UNAUTHORIZED"],
            headers={"WWW-Authenticate": "Basic"}
        )
    return credentials

@log_execution_time("sort_and_reorder_dict")
def sort_and_reorder_dict(raw: dict, field_order: list) -> dict:
    """
    Ordena o dict pela chave (A-Z) e reordena os campos internos conforme field_order.
    Suporta chaves str ou int com performance otimizada.
    """
    def reorder(item: dict) -> dict:
        # Usa dict comprehension para melhor performance
        ordered = {k: item[k] for k in field_order if k in item}
        # Adiciona campos não especificados na ordem
        ordered.update({k: v for k, v in item.items() if k not in ordered})
        return ordered

    def sort_key(k):
        """Função de ordenação otimizada."""
        try:
            return (0, int(k))
        except (ValueError, TypeError):
            return (1, str(k).lower())

    # Ordena e reordena em uma operação
    return {
        k: reorder(v) 
        for k, v in sorted(raw.items(), key=lambda kv: sort_key(kv[0]))
    }

# ========== REDIS GLOBAL ==========

redis = Redis.from_env()

# ========== ENDPOINTS PRINCIPAIS ==========

@app.get("/")
async def root():
    """Endpoint raiz com informações da API."""
    return {
        "message": f"{api_config.TITLE} - v{api_config.VERSION}",
        "status": "operational",
        "documentation": "/docs" if is_development() else "Contact administrator",
        "monitoring": "/monitoring/health"
    }

# ========== ENDPOINTS DE AUTENTICAÇÃO ==========

@app.get("/api/users")
@log_execution_time("get_users")
@handle_errors
@retry_external_api
async def get_users(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém lista de usuários com cache otimizado."""
    cache_key = CACHE_KEYS["users"]
    field_order = FIELD_ORDERS["users"]
    
    # Tenta obter do cache
    cache = get_cache()
    cached_data = await cache.get(cache_key)
    
    if cached_data:
        api_logger.log_endpoint_call("get_users", credentials.username, cache_hit=True)
        return sort_and_reorder_dict(cached_data, field_order)
    
    # Busca dados frescos
    users_data = jsonable_encoder(await fetch_users_from_pipefy())
    ordered_data = sort_and_reorder_dict(users_data, field_order)
    
    # Armazena no cache
    await cache.set(cache_key, ordered_data, cache_config.USERS_TTL)
    
    api_logger.log_endpoint_call("get_users", credentials.username, cache_hit=False)
    return ordered_data
    
@app.post("/api/login")
@log_execution_time("login")
async def validate_login(payload: LoginRequest):
    """Endpoint de autenticação de usuários."""
    api_logger.log_endpoint_call("login", user_email=payload.email)
    return await login(payload.email, payload.password)

@app.post("/api/verify-token")
@log_execution_time("verify_token")
async def verify_user_token(payload: VerifyToken):
    """Verifica validade de token de usuário."""
    return await verify_token(payload.token)

@app.post("/api/password-hash")
@log_execution_time("password_hash")
async def hash_password(payload: PasswordHashRequest):
    """Gera hash de senha para usuário."""
    return await create_password_hash(payload.password, payload.card_id)

@app.post("/api/hash-reset-code")
@log_execution_time("hash_reset_code")
async def hash_reset_code(payload: HashResetCodeRequest):
    """Gera hash para código de reset."""
    return await create_code_hash(code=payload.code)

@app.post("/api/reset-password")
@log_execution_time("reset_password")
async def reset_user_password(payload: ResetPasswordRequest):
    """Redefine senha do usuário."""
    api_logger.log_endpoint_call("reset_password", user_id=payload.user_id)
    return await reset_password(payload.user_id, payload.new_password)

@app.post("/api/reset-code")
@log_execution_time("reset_code")
async def send_reset_code(payload: ResetCodeRequest):
    """Envia código de reset para usuário."""
    api_logger.log_endpoint_call("reset_code", card_id=payload.card_id)
    return await reset_code(payload.card_id, payload.email)

@app.post("/api/forgot-password")
@log_execution_time("forgot_password")
async def user_forgot_password(payload: ForgotPasswordRequest):
    """Inicia processo de recuperação de senha."""
    api_logger.log_endpoint_call("forgot_password", email=payload.email)
    return await forgot_password(payload.email)

@app.post("/api/verify-password")
@log_execution_time("verify_password")
async def verify_user_password(payload: VerifyPasswordRequest):
    """Verifica se senha confere com hash."""
    return verify_password(payload.password, payload.hashed_password)

@app.post("/api/verify-reset-code")
@log_execution_time("verify_reset_code")
async def verify_code(payload: VerifyResetCodeRequest):
    """Verifica código de reset."""
    return await verify_reset_code(
        submited_code=payload.submited_code, 
        reset_code=payload.reset_code
    )

# ========== ENDPOINTS DE CURSOS ==========

@app.post("/update-course-status")
@log_execution_time("update_course_status")
async def update_course_status_after_comite(
    courseId: str, 
    status: str, 
    observations: str, 
    credentials: HTTPBasicCredentials = Depends(verify_basic_auth)
):
    """Atualiza status de curso após comitê."""
    course = CourseUpdate(
        courseId=str(courseId),
        status=status,
        observations=observations
    )
    
    api_logger.log_endpoint_call(
        "update_course_status", 
        credentials.username, 
        course_id=courseId,
        new_status=status
    )
    
    # Invalida cache relacionado
    cache = get_cache()
    await cache.delete_pattern("*home_data*")
    await cache.delete_pattern("*courses_data*")
    
    message = await update_course_status(course)
    return message

@app.get("/courses")
@log_execution_time("get_courses_unyleya")
@handle_errors
@retry_external_api
async def get_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém dados de cursos Unyleya com cache otimizado."""
    cache_key = CACHE_KEYS["courses_unyleya"]
    field_order = FIELD_ORDERS["courses_unyleya"]
    
    # Tenta obter do cache
    cache = get_cache()
    cached_data = await cache.get(cache_key)
    
    if cached_data:
        api_logger.log_endpoint_call("get_courses", credentials.username, cache_hit=True)
        return sort_and_reorder_dict(cached_data, field_order)
    
    # Busca dados frescos
    courses_data = jsonable_encoder(await get_courses_unyleya())
    ordered_data = sort_and_reorder_dict(courses_data, field_order)
    
    # Armazena no cache
    await cache.set(cache_key, ordered_data, cache_config.COURSES_TTL)
    
    api_logger.log_endpoint_call("get_courses", credentials.username, cache_hit=False)
    return ordered_data

@app.get("/courses-ymed")
@log_execution_time("get_courses_ymed")
async def get_ymed_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém dados de cursos YMED com cache otimizado."""
    cache_key = CACHE_KEYS["courses_ymed"]
    field_order = FIELD_ORDERS["courses_ymed"]
    
    # Tenta obter do cache
    cache = get_cache()
    cached_data = await cache.get(cache_key)
    
    if cached_data:
        api_logger.log_endpoint_call("get_courses_ymed", credentials.username, cache_hit=True)
        return sort_and_reorder_dict(cached_data, field_order)
    
    # Busca dados frescos
    courses_data = jsonable_encoder(await get_courses_ymed())
    ordered_data = sort_and_reorder_dict(courses_data, field_order)
    
    # Armazena no cache
    await cache.set(cache_key, ordered_data, cache_config.COURSES_TTL)
    
    api_logger.log_endpoint_call("get_courses_ymed", credentials.username, cache_hit=False)
    return ordered_data

@app.get("/home-data")
@log_execution_time("get_home_data")
async def home_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém dados do dashboard com cache otimizado."""
    cache_key = CACHE_KEYS["home_data"]
    field_order = FIELD_ORDERS["home_data"]
    
    # Tenta obter do cache
    cache = get_cache()
    cached_data = await cache.get(cache_key)
    
    if cached_data:
        api_logger.log_endpoint_call("get_home_data", credentials.username, cache_hit=True)
        return sort_and_reorder_dict(cached_data, field_order)
    
    # Busca dados frescos
    home_data_dict = await get_home_data()
    ordered_data = sort_and_reorder_dict(home_data_dict, field_order)
    
    # Armazena no cache
    await cache.set(cache_key, ordered_data, cache_config.DEFAULT_TTL)
    
    api_logger.log_endpoint_call("get_home_data", credentials.username, cache_hit=False)
    return ordered_data

@app.get("/get-card-comments")
@log_execution_time("get_card_comments")
async def get_card_comments(
    card_id: int, 
    credentials: HTTPBasicCredentials = Depends(verify_basic_auth)
):
    """Obtém comentários de um card."""
    api_logger.log_endpoint_call("get_card_comments", credentials.username, card_id=card_id)
    return await get_card_comments_data(card_id=card_id)

@app.post("/create-card-comment")
@log_execution_time("create_card_comment")
async def create_card_comment(
    card_id: int, 
    text: str, 
    credentials: HTTPBasicCredentials = Depends(verify_basic_auth)
):
    """Cria comentário em um card."""
    api_logger.log_endpoint_call("create_card_comment", credentials.username, card_id=card_id)
    return await create_comment_in_card(card_id=card_id, text=text)

# ========== ENDPOINTS DE REFRESH ==========

@app.get("/refresh-courses-unyleya")
@log_execution_time("refresh_courses_unyleya")
async def refresh_courses_unyleya(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpa cache e recarrega dados de cursos Unyleya."""
    cache = get_cache()
    await cache.delete(CACHE_KEYS["courses_unyleya"])
    
    api_logger.log_endpoint_call("refresh_courses_unyleya", credentials.username)
    return await get_courses_data(credentials)

@app.get("/refresh-courses-ymed")
@log_execution_time("refresh_courses_ymed")
async def refresh_courses_ymed(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpa cache e recarrega dados de cursos YMED."""
    cache = get_cache()
    await cache.delete(CACHE_KEYS["courses_ymed"])
    
    api_logger.log_endpoint_call("refresh_courses_ymed", credentials.username)
    return await get_ymed_courses_data(credentials)

@app.get("/refresh-home-data")
@log_execution_time("refresh_home_data")
async def refresh_home_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpa cache e recarrega dados do dashboard."""
    cache = get_cache()
    await cache.delete(CACHE_KEYS["home_data"])
    
    api_logger.log_endpoint_call("refresh_home_data", credentials.username)
    return await home_data(credentials)

@app.get("/refresh-users")
@log_execution_time("refresh_users")
async def refresh_users(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpa cache e recarrega dados de usuários."""
    cache = get_cache()
    await cache.delete(CACHE_KEYS["users"])
    
    api_logger.log_endpoint_call("refresh_users", credentials.username)
    return await get_users(credentials)

@app.get("/refresh-data")
@log_execution_time("refresh_all_data")
async def refresh_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpa todos os caches e recarrega dados."""
    api_logger.log_endpoint_call("refresh_all_data", credentials.username)
    
    # Executa refreshes em paralelo para melhor performance
    results = await asyncio.gather(
        refresh_courses_unyleya(credentials),
        refresh_courses_ymed(credentials),
        refresh_home_data(credentials),
        refresh_users(credentials),
        return_exceptions=True
    )
    
    # Conta sucessos e falhas
    successes = sum(1 for r in results if not isinstance(r, Exception))
    failures = len(results) - successes
    
    return {
        "message": "Atualização de dados concluída",
        "successes": successes,
        "failures": failures,
        "total_operations": len(results)
    }

# ========== ENDPOINTS G2 ==========

@app.get("/g2/cursos-g2")
@log_execution_time("get_g2_courses")
async def get_cursos_g2_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém dados de cursos G2."""
    api_logger.log_endpoint_call("get_g2_courses", credentials.username)
    return await get_g2_courses_api()

@app.get("/g2/cursos-g2-excel")
@log_execution_time("get_g2_courses_excel")
async def get_cursos_g2_excel_file(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Download de cursos G2 em Excel."""
    api_logger.log_endpoint_call("get_g2_courses_excel", credentials.username)
    return await get_g2_courses_excel()

@app.get("/g2/cursos-search")
@log_execution_time("get_g2_search")
async def get_cursos_search_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Obtém dados de cursos para busca."""
    api_logger.log_endpoint_call("get_g2_search", credentials.username)
    return await get_search_courses_api()

@app.post("/g2/refresh-cursos")
@log_execution_time("refresh_g2_courses")
async def refresh_g2_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Atualiza caches dos cursos G2."""
    api_logger.log_endpoint_call("refresh_g2_courses", credentials.username)
    return await refresh_all_caches()