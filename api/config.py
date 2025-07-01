"""
Configurações centralizadas da API NPI-backend.
Contém constantes, configurações de ambiente e parâmetros globais.
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Carrega variáveis de ambiente
if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()

@dataclass
class CacheConfig:
    """Configurações de cache Redis."""
    DEFAULT_TTL: int = 1800  # 30 minutos
    COURSES_TTL: int = 3600  # 1 hora
    USERS_TTL: int = 7200    # 2 horas
    G2_COURSES_TTL: int = 1800  # 30 minutos

@dataclass
class APIConfig:
    """Configurações gerais da API."""
    VERSION: str = "2.0.0"
    TITLE: str = "API de Cursos da Unyleya"
    DESCRIPTION: str = "API para gerenciamento de cursos e dados acadêmicos"
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    
    # Timeouts
    HTTP_TIMEOUT: float = 30.0
    REDIS_TIMEOUT: float = 5.0
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # segundos

@dataclass
class AuthConfig:
    """Configurações de autenticação."""
    TOKEN_EXPIRE_HOURS: int = 24
    ALGORITHM: str = "HS256"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key")

@dataclass
class LogConfig:
    """Configurações de logging."""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    FORMAT: str = "[{time}] [{level}] {name}: {message}"
    ROTATION: str = "1 day"
    RETENTION: str = "30 days"

# Constantes de ordenação de campos
FIELD_ORDERS = {
    "users": [
        "id", "nome", "email", "password", "permissao", "card_id"
    ],
    "courses_unyleya": [
        "id", "entity", "slug", "nome", "coordenadorSolicitante", "coordenadores",
        "apresentacao", "publico", "concorrentesIA", "performance",
        "videoUrl", "disciplinasIA", "status", "observacoesComite", "cargaHoraria"
    ],
    "courses_ymed": [
        "id", "entity", "slug", "nomeDoCurso", "coordenador", "justificativaIntroducao",
        "lacunaFormacaoGap", "propostaCurso", "publicoAlvo", "conteudoProgramatico",
        "mercado", "diferencialCurso", "observacoesGerais", "status", "observacoesComite",
        "performance", "concorrentes"
    ],
    "home_data": [
        "active_projects", "coordinators", "rejected", "approved", "pendent",
        "standby", "total_proposals", "unyleya_proposals", "ymed_proposals"
    ]
}

# Chaves de cache
CACHE_KEYS = {
    "users": "users_data",
    "courses_unyleya": "courses_data", 
    "courses_ymed": "ymed_courses_data",
    "home_data": "home_data",
    "g2_courses": "cursos_g2_data",
    "search_courses": "cursos_search_data",
    "dataframe": "cursos_dataframe"
}

# Headers CORS padrão
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
}

# Status HTTP customizados
HTTP_STATUS = {
    "CACHE_HIT": 200,
    "CACHE_MISS": 200,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
    "SERVICE_UNAVAILABLE": 503
}

# Mensagens de erro padrão
ERROR_MESSAGES = {
    "UNAUTHORIZED": "Credenciais inválidas",
    "FORBIDDEN": "Acesso negado para este recurso",
    "NOT_FOUND": "Recurso não encontrado",
    "RATE_LIMITED": "Muitas requisições. Tente novamente em alguns minutos",
    "INTERNAL_ERROR": "Erro interno do servidor",
    "SERVICE_UNAVAILABLE": "Serviço temporariamente indisponível",
    "CACHE_ERROR": "Erro no sistema de cache",
    "DATABASE_ERROR": "Erro de conexão com banco de dados"
}

# Configurações das instâncias
cache_config = CacheConfig()
api_config = APIConfig()
auth_config = AuthConfig()
log_config = LogConfig()

def get_basic_auth_users() -> Dict[str, str]:
    """Extrai usuários de autenticação básica das variáveis de ambiente."""
    users = {}
    users_env = os.getenv("BASIC_AUTH_USERS")
    if users_env:
        for pair in users_env.split(","):
            if ":" in pair:
                user, pwd = pair.split(":", 1)
                users[user.strip()] = pwd.strip()
    return users

def get_allowed_origins() -> List[str]:
    """Obtém lista de origens permitidas para CORS."""
    origins_env = os.getenv("ALLOWED_ORIGINS", "*")
    if origins_env == "*":
        return ["*"]
    return [origin.strip() for origin in origins_env.split(",")]

def is_development() -> bool:
    """Verifica se está em ambiente de desenvolvimento."""
    return os.getenv("ENVIRONMENT", "production").lower() == "development"

def is_production() -> bool:
    """Verifica se está em ambiente de produção."""
    return os.getenv("ENVIRONMENT", "production").lower() == "production"

@dataclass
class SecurityConfig:
    """Configurações de segurança."""
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # segundos
    SUSPICIOUS_REQUEST_THRESHOLD: int = 500
    BLOCK_DURATION_MINUTES: int = 15
    
    # Validação de entrada
    MIN_PASSWORD_LENGTH: int = 8
    MAX_PASSWORD_LENGTH: int = 128
    REQUIRE_SPECIAL_CHARS: bool = True
    MAX_PAYLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # Headers de segurança
    ENABLE_SECURITY_HEADERS: bool = True
    STRICT_TRANSPORT_SECURITY: bool = True

@dataclass
class CompressionConfig:
    """Configurações de compressão."""
    # Tipos de compressão
    ENABLE_GZIP: bool = True
    ENABLE_BROTLI: bool = True
    ENABLE_DEFLATE: bool = False
    
    # Parâmetros de compressão
    MIN_SIZE_TO_COMPRESS: int = 1024  # 1KB
    GZIP_LEVEL: int = 6
    BROTLI_QUALITY: int = 4
    DEFLATE_LEVEL: int = 6
    
    # Otimizações
    USE_ORJSON: bool = True

@dataclass
class MonitoringConfig:
    """Configurações de monitoramento."""
    # Métricas
    ENABLE_METRICS: bool = True
    METRICS_RETENTION_HOURS: int = 24
    MAX_METRICS_POINTS: int = 10000
    
    # Health check
    HEALTH_CHECK_TIMEOUT: float = 5.0
    EXTERNAL_SERVICES_CHECK: bool = True
    
    # Performance
    SLOW_REQUEST_THRESHOLD: float = 1.0  # segundos
    MEMORY_ALERT_THRESHOLD: float = 0.85  # 85%

@dataclass
class RetryConfig:
    """Configurações de retry."""
    # Retry geral
    MAX_RETRIES: int = 3
    BASE_DELAY: float = 1.0
    MAX_DELAY: float = 60.0
    BACKOFF_FACTOR: float = 2.0
    
    # Circuit breaker
    CIRCUIT_FAILURE_THRESHOLD: int = 5
    CIRCUIT_RECOVERY_TIMEOUT: int = 60

# Configurações das instâncias
cache_config = CacheConfig()
api_config = APIConfig()
auth_config = AuthConfig()
log_config = LogConfig()
security_config = SecurityConfig()
compression_config = CompressionConfig()
monitoring_config = MonitoringConfig()
retry_config = RetryConfig()

# Configurações específicas por ambiente
if is_development():
    api_config.DOCS_URL = "/docs"
    api_config.REDOC_URL = "/redoc"
    log_config.LEVEL = "DEBUG"
    security_config.RATE_LIMIT_REQUESTS = 1000  # Mais permissivo em dev
    compression_config.MIN_SIZE_TO_COMPRESS = 512  # Menor threshold em dev
    monitoring_config.SLOW_REQUEST_THRESHOLD = 2.0  # Mais tolerante em dev
else:
    api_config.DOCS_URL = None  # Desabilita docs em produção
    api_config.REDOC_URL = None
    log_config.LEVEL = "WARNING"
    security_config.RATE_LIMIT_REQUESTS = 50  # Mais restritivo em produção
    compression_config.MIN_SIZE_TO_COMPRESS = 2048  # Maior threshold em produção
    monitoring_config.SLOW_REQUEST_THRESHOLD = 0.5  # Mais rigoroso em produção
