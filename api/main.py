from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.encoders import jsonable_encoder
from upstash_redis import Redis
import os
import warnings
from dotenv import load_dotenv
import secrets
from .lib.models import *
from .scripts.courses import *
from .scripts.login import *
from .scripts.g2_cursos import *
import asyncio

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
    # Inicializa os usuários do Pipefy
    global users
    users = await fetch_users_from_pipefy()
    if not users:
        raise HTTPException(status_code=500, detail="Erro ao buscar usuários do Pipefy")
    yield

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas as origens
    allow_methods=["*"],
    allow_headers=["*"],
)

redis = Redis.from_env()

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
    
@app.get("/courses")
async def get_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    cache_key = "courses_data"
    field_order = [
        "id", "entity", "slug", "nome", "coordenadorSolicitante", "coordenadores",
        "apresentacao", "publico", "concorrentesIA", "performance",
        "videoUrl", "disciplinasIA", "status", "observacoesComite", "cargaHoraria"
    ]
    cached = redis.json.get(cache_key)
    if cached:
        raw = cached[0]
        return sort_and_reorder_dict(raw, field_order)
    raw = jsonable_encoder(await get_courses_unyleya())
    ordered = sort_and_reorder_dict(raw, field_order)
    redis.json.set(cache_key, path="$", value=ordered, nx=True)
    return ordered

@app.get("/courses-ymed")
async def get_ymed_courses_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    cache_key = "ymed_courses_data"
    field_order = [
        "id", "entity", "slug", "nomeDoCurso", "coordenador", "justificativaIntroducao",
        "lacunaFormacaoGap", "propostaCurso", "publicoAlvo", "conteudoProgramatico",
        "mercado", "diferencialCurso", "observacoesGerais", "status", "observacoesComite",
        "performance", "concorrentes"
    ]
    cached = redis.json.get(cache_key)
    if cached:
        raw = cached[0]
        return sort_and_reorder_dict(raw, field_order)
    raw = jsonable_encoder(await get_courses_ymed())
    ordered = sort_and_reorder_dict(raw, field_order)
    redis.json.set(cache_key, path="$", value=ordered, nx=True)
    return ordered

@app.get("/home-data")
async def home_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
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

# Cursos Refresh Functions
@app.post("/g2/refresh-cursos")
async def refresh_data(credentials: HTTPBasicCredentials = Depends(verify_basic_auth)):
    return await refresh_cursos_g2()