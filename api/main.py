from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from .models import CourseUpdate
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis
from .utils.courses import *
from .utils.login import *
import warnings
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

async def lifespan(app: FastAPI):
    # Configuração do Redis
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    
    # Inicializa os usuários do Pipefy
    global users
    users = await fetch_users_from_pipefy()
    if not users:
        raise HTTPException(status_code=500, detail="Erro ao buscar usuários do Pipefy")
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas as origens
    allow_methods=["*"],
    allow_headers=["*"],
)


if not REDIS_URL:
    raise ValueError("REDIS_URL não está definida nas variáveis de ambiente")

@app.get("/")
async def root():
    return {"message": "API de Cursos da Unyleya - Versão 1.0"}

@app.get("/courses")
@cache(expire=300)  # Cache por 5 minutos
async def get_courses_data():
    return await get_courses_unyleya()

@app.post("/update-course-status")
async def update_course_status_after_comite(courseId: str, status: str, observations: str):
    course = CourseUpdate(
        courseId=str(courseId),
        status=status,
        observations=observations
    )
    return await update_course_status(course)
    
@app.get("/refresh-courses")
async def refresh_courses():
    """Clear cached course data and fetch fresh information."""
    await FastAPICache.clear()
    # call the underlying function without cache decorator context
    courses = await get_courses_data.__wrapped__()
    return courses

@app.get("/api/users")
async def get_users():
    return await fetch_users_from_pipefy()

@app.post("/api/login")
async def validate_login(email: str, password: str):
    return await login(email, password)

@app.post("/api/verify-token")
async def verify_user_token(token: str):
    return await verify_token(token)

@app.post("/api/password-hash")
async def hash_password(password: str, card_id: int):
    return await create_password_hash(password, card_id)

@app.post("/api/reset-password")
async def reset_user_password(user_id: str, new_password: str):
    return await reset_password(user_id, new_password)

@app.post("/api/reset-code")
async def send_reset_code(email: str, card_id: int):
    return await reset_code(card_id, email)

@app.post("/api/forgot-password")
async def user_forgot_password(email: str):
    return await forgot_password(email)

@app.post("/api/verify-password")
async def verify_user_password(password: str, hashed_password: str):
    return verify_password(password, hashed_password)

@app.get("/courses-ymed")
@cache(expire=300)
async def get_ymed_courses_data():
    return await get_courses_ymed()

@app.get("/refresh-courses-ymed")
async def refresh_courses():
    """Clear cached course data and fetch fresh information."""
    await FastAPICache.clear()
    # call the underlying function without cache decorator context
    courses = await get_ymed_courses_data.__wrapped__()
    return courses