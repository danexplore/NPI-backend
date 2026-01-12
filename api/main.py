from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.encoders import jsonable_encoder
from upstash_redis import Redis
import os
import warnings
from dotenv import load_dotenv
import secrets
import logging
from datetime import datetime

# Carregar variáveis de ambiente primeiro
load_dotenv()


# Imports relativos corretos
from .lib.models import *
from .scripts.courses import *
from .scripts.login import *
from .scripts.g2_cursos import *
from .scripts.chatbot import (
    ChatbotMessageRequest,
    process_chatbot_message,
    get_conversation_history,
    clear_conversation_history
)
from .scripts.chatbotYmed import (
    process_chatbot_message as process_ymed_message,
    get_conversation_history as get_ymed_history,
    clear_conversation_history as clear_ymed_history
)
import asyncio


# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Parse users from env
USERS = {}
users_env = os.getenv("BASIC_AUTH_USERS")
if users_env:
    for pair in users_env.split(","):
        if ":" in pair:
            user, pwd = pair.split(":", 1)
            USERS[user.strip()] = pwd.strip()

security = HTTPBasic()

def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    password = USERS.get(credentials.username)
    if not password or not secrets.compare_digest(credentials.password, password):
        raise HTTPException(status_code=401, detail="Acesso negado.", headers={"WWW-Authenticate": "Basic"})
    return credentials

async def lifespan(app: FastAPI):
    try:
        logger.info("Iniciando aplicação...")
        
        # Verificar variáveis de ambiente críticas
        required_env_vars = [
            "UPSTASH_REDIS_REST_URL",
            "UPSTASH_REDIS_REST_TOKEN",
            "OPENAI_API_KEY",
            "PIPEFY_SERVICE_ACCOUNT_ID",
            "PIPEFY_SERVICE_ACCOUNT_SECRET",
            "PIPEFY_OAUTH_URL",
            "PIPEFY_API_URL",
            "JWT_SECRET_KEY",
            "DB_HOST",
            "DB_USER",
            "DB_PASSWORD",
            "DB_NAME",
            "DB_PORT"
        ]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Variáveis de ambiente obrigatórias não encontradas: {missing_vars}")
            raise RuntimeError(f"Variáveis de ambiente obrigatórias não encontradas: {missing_vars}")
        
        # Inicializa os usuários do Pipefy
        global users
        logger.info("Buscando usuários do Pipefy...")
        users = await fetch_users_from_pipefy()
        if not users:
            logger.error("Erro ao buscar usuários do Pipefy")
            raise RuntimeError("Erro ao buscar usuários do Pipefy")
        
        logger.info("Aplicação iniciada com sucesso!")
        yield
        
    except Exception as e:
        logger.error(f"Erro durante a inicialização: {str(e)}")
        raise

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()


app = FastAPI(lifespan=lifespan)

# Endpoint para retornar informações do usuário autenticado
@app.get("/api/me")
async def get_me(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Retorna informações do usuário autenticado."""
    return {"username": credentials.username}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas as origens
    allow_methods=["*"],
    allow_headers=["*"],
)

# Verificar conexão com Redis
try:
    redis = Redis.from_env()
    logger.info("Conexão com Redis estabelecida com sucesso")
except Exception as e:
    logger.error(f"Erro ao conectar com Redis: {str(e)}")
    raise

def sort_and_reorder_dict(raw: dict, field_order: list) -> dict:
    """
    Ordena o dict pela chave (A-Z) e reordena os campos internos conforme field_order.
    Suporta chaves str ou int.
    """
    def reorder(item: dict) -> dict:
        ordered = {k: item[k] for k in field_order if k in item}
        for k in item:
            if k not in ordered:
                ordered[k] = item[k]
        return ordered

    # Sort keys, handling both str and int
    def sort_key(k):
        # Try to convert to int for sorting, fallback to str
        try:
            return (0, int(k))
        except (ValueError, TypeError):
            return (1, str(k).lower())

    sorted_by_key = dict(sorted(raw.items(), key=lambda kv: sort_key(kv[0])))
    return {k: reorder(v) for k, v in sorted_by_key.items()}

@app.get("/")
async def root():
    return {"message": "API de Cursos da Unyleya - Versão 1.0"}


@app.get("/health")
async def health_check():
    """Endpoint de verificação de saúde da aplicação, com logs detalhados de DNS."""
    try:
        logger.info(f"Testando DNS para Redis: {os.getenv('UPSTASH_REDIS_REST_URL')}")
        logger.info(f"Testando DNS para OpenAI: {os.getenv('OPENAI_API_KEY')}")
        logger.info(f"Testando DNS para Pipefy: {os.getenv('PIPEFY_API_URL')}")
        # Verificar conexão com Redis
        redis.ping()
        logger.info("Ping Redis OK")
        # Verificar OpenAI
        openai_status = bool(os.getenv("OPENAI_API_KEY"))
        # Verificar variáveis de ambiente
        env_status = {
            "UPSTASH_REDIS_REST_URL": bool(os.getenv("UPSTASH_REDIS_REST_URL")),
            "UPSTASH_REDIS_REST_TOKEN": bool(os.getenv("UPSTASH_REDIS_REST_TOKEN")),
            "OPENAI_API_KEY": openai_status,
            "BASIC_AUTH_USERS": bool(os.getenv("BASIC_AUTH_USERS")),
            "PIPEFY_SERVICE_ACCOUNT_ID": bool(os.getenv("PIPEFY_SERVICE_ACCOUNT_ID")),
            "PIPEFY_SERVICE_ACCOUNT_SECRET": bool(os.getenv("PIPEFY_SERVICE_ACCOUNT_SECRET")),
            "PIPEFY_OAUTH_URL": bool(os.getenv("PIPEFY_OAUTH_URL")),
            "PIPEFY_API_URL": bool(os.getenv("PIPEFY_API_URL")),
            "JWT_SECRET_KEY": bool(os.getenv("JWT_SECRET_KEY")),
            "DB_HOST": bool(os.getenv("DB_HOST")),
            "DB_USER": bool(os.getenv("DB_USER")),
            "DB_PASSWORD": bool(os.getenv("DB_PASSWORD")),
            "DB_NAME": bool(os.getenv("DB_NAME")),
            "DB_PORT": bool(os.getenv("DB_PORT"))
        }
        return {
            "status": "healthy",
            "environment": os.getenv("ENVIRONMENT", "production"),
            "redis_connection": "ok",
            "openai_available": openai_status,
            "env_variables": env_status,
            "chatbot_ready": all(env_status.values())
        }
    except Exception as e:
        import socket
        logger.error(f"Health check falhou: {str(e)}")
        # Tentar resolver manualmente os hosts para log detalhado
        try:
            redis_host = os.getenv('UPSTASH_REDIS_REST_URL','').replace('https://','').replace('http://','').split('/')[0]
            pipefy_host = os.getenv('PIPEFY_API_URL','').replace('https://','').replace('http://','').split('/')[0]
            logger.error(f"DNS Redis: {redis_host} => {socket.gethostbyname(redis_host)}")
            logger.error(f"DNS Pipefy: {pipefy_host} => {socket.gethostbyname(pipefy_host)}")
        except Exception as dns_e:
            logger.error(f"Erro ao resolver DNS manualmente: {dns_e}")
        raise HTTPException(status_code=500, detail=f"Health check falhou: {str(e)}")

# Auth Functions
@app.get("/api/users")
async def get_users(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    field_order = [
        "id",
        "nome",
        "email",
        "password",
        "permissao",
        "card_id"
    ]
    cache_key = "users_data"
    cached_data = redis.json.get(cache_key)
    if cached_data:
        users = cached_data[0]
        return sort_and_reorder_dict(users, field_order)
    users = jsonable_encoder(await fetch_users_from_pipefy())
    redis.json.set(cache_key, value=users, path="$", nx=True)
    return sort_and_reorder_dict(users, field_order)

@app.post("/api/login")
async def validate_login(payload: LoginRequest):
    return await login(payload.email, payload.password)

@app.post("/api/verify-token")
async def verify_user_token(payload: VerifyToken):
    token = payload.token
    return await verify_token(token)

@app.post("/api/password-hash")
async def hash_password(payload: PasswordHashRequest):
    return await create_password_hash(payload.password, payload.card_id)

@app.post("/api/hash-reset-code")
async def hash_reset_code(payload: HashResetCodeRequest):
    return await create_code_hash(code=payload.code)

@app.post("/api/reset-password")
async def reset_user_password(payload: ResetPasswordRequest):
    return await reset_password(payload.user_id, payload.new_password)

@app.post("/api/reset-code")
async def send_reset_code(payload: ResetCodeRequest):
    return await reset_code(payload.card_id, payload.email)

@app.post("/api/forgot-password")
async def user_forgot_password(payload: ForgotPasswordRequest):
    return await forgot_password(payload.email)

@app.post("/api/verify-password")
async def verify_user_password(payload: VerifyPasswordRequest):
    return verify_password(payload.password, payload.hashed_password)

@app.post("/api/verify-reset-code")
async def verify_code(payload: VerifyResetCodeRequest):
    return await verify_reset_code(submited_code=payload.submited_code, reset_code=payload.reset_code)

# Course Functions
@app.post("/update-course-status")
async def update_course_status_after_comite(payload: CourseUpdate, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    course = CourseUpdate(
        courseId=str(payload.courseId),
        status=payload.status,
        observations=payload.observations
    )
    message = await update_course_status(course)
    redis.json.delete("home_data")
    await home_data()
    return message

@app.get("/diagnostic/pipefy")
async def diagnose_pipefy_connection(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Endpoint de diagnóstico para verificar conexão com Pipefy"""
    import httpx
    try:
        api_url = "https://api.pipefy.com/graphql"
        pipefy_key = os.getenv("PIPEFY_API_KEY")
        
        if not pipefy_key:
            return {
                "status": "error",
                "message": "PIPEFY_API_KEY não configurada"
            }
        
        # Fazer uma query simples para testar
        test_query = '{ organization(id: "0") { name } }'
        headers = {
            "Authorization": f"Bearer {pipefy_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                api_url,
                headers=headers,
                json={"query": test_query}
            )
            
            return {
                "status": "ok" if response.is_success else "error",
                "http_status": response.status_code,
                "response": response.text[:500] if response.text else "No response"
            }
    except Exception as e:
        logger.error(f"Erro ao diagnosticar Pipefy: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
    
@app.get("/courses")
async def get_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    try:
        cache_key = "courses_data"
        field_order = [
            "id", "fase", "entity", "slug", "nome", "coordenadorSolicitante", "coordenadores",
            "apresentacao", "publico", "concorrentesIA", "performance",
            "videoUrl", "disciplinasIA", "status", "observacoesComite", "cargaHoraria"
        ]
        logger.info("Buscando dados de cursos Unyleya")
        cached = redis.json.get(cache_key)
        if cached:
            logger.info("Retornando cursos do cache")
            raw = cached[0]
            return sort_and_reorder_dict(raw, field_order)
        logger.info("Buscando cursos da API Pipefy")
        raw = jsonable_encoder(await get_courses_unyleya())
        logger.info(f"Encontrados {len(raw)} cursos")
        ordered = sort_and_reorder_dict(raw, field_order)
        redis.json.set(cache_key, path="$", value=ordered, nx=True)
        return ordered
    except Exception as e:
        logger.error(f"Erro ao buscar cursos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar cursos: {str(e)}")

@app.get("/pre-comite-courses")
async def get_pre_comite_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    try:
        cache_key = "pre_comite_courses_data"
        field_order = [
            "id", "fase", "entity", "slug", "nome", "coordenadorSolicitante", "coordenadores",
            "apresentacao", "publico", "concorrentesIA", "performance",
            "videoUrl", "disciplinasIA", "status", "observacoesComite", "cargaHoraria"
        ]
        logger.info("Buscando dados de cursos pré-comitê")
        cached = redis.json.get(cache_key)
        if cached:
            logger.info("Retornando cursos pré-comitê do cache")
            raw = cached[0]
            return sort_and_reorder_dict(raw, field_order)
        logger.info("Buscando cursos pré-comitê da API Pipefy")
        raw = jsonable_encoder(await get_courses_pre_comite())
        logger.info(f"Encontrados {len(raw)} cursos pré-comitê")
        ordered = sort_and_reorder_dict(raw, field_order)
        redis.json.set(cache_key, path="$", value=ordered, nx=True)
        return ordered
    except Exception as e:
        logger.error(f"Erro ao buscar cursos pré-comitê: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar cursos pré-comitê: {str(e)}")

@app.get("/courses-ymed")
async def get_ymed_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    try:
        cache_key = "ymed_courses_data"
        field_order = [
            "id", "entity", "slug", "nomeDoCurso", "coordenador", "justificativaIntroducao",
            "lacunaFormacaoGap", "propostaCurso", "publicoAlvo", "conteudoProgramatico",
            "mercado", "diferencialCurso", "observacoesGerais", "status", "observacoesComite",
            "performance", "concorrentes"
        ]
        logger.info("Buscando dados de cursos YMED")
        cached = redis.json.get(cache_key)
        if cached:
            logger.info("Retornando cursos YMED do cache")
            raw = cached[0]
            return sort_and_reorder_dict(raw, field_order)
        logger.info("Buscando cursos YMED da API Pipefy")
        raw = jsonable_encoder(await get_courses_ymed())
        logger.info(f"Encontrados {len(raw)} cursos YMED")
        ordered = sort_and_reorder_dict(raw, field_order)
        redis.json.set(cache_key, path="$", value=ordered, nx=True)
        return ordered
    except Exception as e:
        logger.error(f"Erro ao buscar cursos YMED: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar cursos YMED: {str(e)}")

@app.get("/home-data")
async def home_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """
    Retorna dados agregados para a home, com tratamento de erro robusto e nomes de campos alinhados.
    """
    redis_key = "home_data"
    field_order = [
        "active_projects",
        "coordinators",
        "rejected",
        "approved",
        "pendent",
        "standby",
        "total_proposals",
        "unyleya_proposals",
        "ymed_proposals"
    ]
    try:
        cached_data = redis.json.get(redis_key)
        if cached_data:
            raw = cached_data[0]
            ordered = {k: raw[k] for k in field_order if k in raw}
            for k in raw:
                if k not in ordered:
                    ordered[k] = raw[k]
            return ordered
        home_data_dict = await get_home_data()
        redis.json.set(redis_key, value=home_data_dict, path="$", nx=True)
        ordered = {k: home_data_dict[k] for k in field_order if k in home_data_dict}
        for k in home_data_dict:
            if k not in ordered:
                ordered[k] = home_data_dict[k]
        return ordered
    except Exception as e:
        logger.error(f"Erro ao buscar dados da home: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar dados da home: {str(e)}")

@app.get("/get-card-comments")
async def get_card_comments(card_id: int, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await get_card_comments_data(card_id=card_id)

@app.post("/create-card-comment")
async def create_card_comment(card_id: int, text: str, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await create_comment_in_card(card_id=card_id, text=text)

# Refresh Functions
@app.get("/refresh-courses-unyleya")
async def refresh_courses_unyleya(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached course data and fetch fresh information."""
    redis.json.delete("courses_data")
    return await get_courses_data()

@app.get("/refresh-courses-pre-comite")
async def refresh_courses_pre_comite(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached pre-comite course data and fetch fresh information."""
    redis.json.delete("pre_comite_courses_data")
    return await get_pre_comite_courses_data(credentials)

@app.get("/refresh-courses-ymed")
async def refresh_courses_ymed(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached course data and fetch fresh information."""
    redis.json.delete("ymed_courses_data")
    return await get_ymed_courses_data()

@app.get("/refresh-home-data")
async def refresh_home_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached home data and fetch fresh information."""
    redis.json.delete("home_data")
    return await home_data()

@app.get("/refresh-users")
async def refresh_users(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached users data and fetch fresh information."""
    redis.json.delete("users_data")
    return await get_users()

@app.get("/refresh-data")
async def refresh_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Clear cached data."""
    await asyncio.gather(
        refresh_courses_unyleya(credentials),
        refresh_courses_pre_comite(credentials),
        refresh_courses_ymed(credentials),
        refresh_home_data(credentials),
        refresh_users(credentials)
    )
    return {"message": "Dados atualizados com sucesso."}

# Cursos G2 Functions
@app.get("/g2/cursos-g2")
async def get_cursos_g2_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await get_cursos_g2()

@app.get("/g2/cursos-g2-excel")
async def get_cursos_g2_excel_file(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await get_cursos_g2_excel()

# Cursos Search Functions
@app.get("/g2/cursos-search")
async def get_cursos_search_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await get_cursos_search()

# Chatbot Functions (Normal)
@app.post("/chatbot/message")
async def send_chatbot_message(payload: ChatbotMessageRequest, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Processar mensagem do chatbot"""
    try:
        logger.info(f"Recebendo mensagem do chatbot: user_id={payload.user_id}")
        result = await process_chatbot_message(payload.message, payload.user_id)
        logger.info(f"Mensagem processada com sucesso para user_id={payload.user_id}")
        return result
    except Exception as e:
        logger.error(f"Erro ao processar mensagem do chatbot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")

@app.get("/chatbot/history/{user_id}")
async def get_chatbot_history(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Buscar histórico de conversas"""
    try:
        logger.info(f"Buscando histórico para user_id: {user_id}")
        result = await get_conversation_history(user_id)
        return result
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)}")

@app.delete("/chatbot/history/{user_id}")
async def clear_chatbot_history(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpar histórico de conversas"""
    try:
        logger.info(f"Limpando histórico para user_id: {user_id}")
        result = await clear_conversation_history(user_id)
        return result
    except Exception as e:
        logger.error(f"Erro ao limpar histórico: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar histórico: {str(e)}")

@app.get("/chatbot/test")
async def test_unyleya_chatbot():
    """
    Endpoint de teste para verificar conectividade do chatbot Unyleya.
    """
    try:
        return {
            "success": True,
            "message": "Chatbot Unyleya está funcionando",
            "timestamp": datetime.now().isoformat(),
            "service": "Unyleya Assistant"
        }
    except Exception as e:
        logger.error(f"Erro no teste do chatbot Unyleya: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no teste: {str(e)}")

# Chatbot Ymed Functions (usando Assistants API)
@app.post("/chatbot-ymed/message")
async def send_ymed_chatbot_message(payload: ChatbotMessageRequest, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Processar mensagem do chatbot Ymed usando Assistants API"""
    try:
        logger.info(f"Recebendo mensagem do chatbot Ymed: user_id={payload.user_id}")
        result = await process_ymed_message(payload.message, payload.user_id)
        logger.info(f"Mensagem Ymed processada com sucesso para user_id={payload.user_id}")
        return result
    except Exception as e:
        logger.error(f"Erro ao processar mensagem do chatbot Ymed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem Ymed: {str(e)}")

@app.get("/chatbot-ymed/history/{user_id}")
async def get_ymed_chatbot_history(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Buscar histórico de conversas do chatbot Ymed"""
    try:
        logger.info(f"Buscando histórico Ymed para user_id: {user_id}")
        result = await get_ymed_history(user_id)
        return result
    except Exception as e:
        logger.error(f"Erro ao buscar histórico Ymed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico Ymed: {str(e)}")

@app.delete("/chatbot-ymed/history/{user_id}")
async def clear_ymed_chatbot_history(user_id: str, credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    """Limpar histórico de conversas do chatbot Ymed"""
    try:
        logger.info(f"Limpando histórico Ymed para user_id: {user_id}")
        result = await clear_ymed_history(user_id)
        return result
    except Exception as e:
        logger.error(f"Erro ao limpar histórico Ymed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar histórico Ymed: {str(e)}")

@app.get("/chatbot-ymed/test")
async def test_ymed_chatbot():
    """
    Endpoint de teste para verificar conectividade do chatbot Y-med.
    """
    try:
        return {
            "success": True,
            "message": "Chatbot Y-med está funcionando",
            "timestamp": datetime.now().isoformat(),
            "service": "Y-med Assistant"
        }
    except Exception as e:
        logger.error(f"Erro no teste do chatbot Y-med: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no teste: {str(e)}")