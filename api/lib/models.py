from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Modelos Pydantic para validação de dados
class CourseUpdate(BaseModel):
    courseId: str
    status: str
    observations: Optional[str] = None
    is_pre_comite: bool

class ConcorrenteIA(BaseModel):
    instituicao: str
    curso: str
    link: str
    valor: str

class DisciplinaIA(BaseModel):
    nome: str
    carga: str
    tipo: str

class Coordenador(BaseModel):
    nome: str
    minibiografia: str
    jaECoordenador: bool

class CourseUnyleya(BaseModel):
    id: str
    entity: str
    fase: str = ""
    slug: str
    nome: str
    coordenadorSolicitante: str
    coordenadores: List[Coordenador]
    apresentacao: str
    publico: str
    concorrentesIA: List[ConcorrenteIA]
    performance: str
    videoUrl: str
    disciplinasIA: List[DisciplinaIA]
    status_pre_comite: Optional[str] = None
    status_pos_comite: Optional[str] = None
    observacoes_pre_comite: Optional[str] = None
    observacoes_pos_comite: Optional[str] = None
    cargaHoraria: int

class CourseYMED(BaseModel):
    id: str
    entity: str
    slug: str
    nomeDoCurso: str
    coordenador: Optional[str] = None
    justificativaIntroducao: str
    lacunaFormacaoGap: str
    propostaCurso: str
    publicoAlvo: str
    conteudoProgramatico: str
    mercado: str
    diferencialCurso: str
    observacoesGerais: str
    status: Optional[str] = None
    observacoesComite: Optional[str] = None
    performance: Optional[str] = None
    concorrentes: List[dict]

class ApiResponse(BaseModel):
    data: Optional[Dict[str, Any]] = None

# Modelos de Auth
class User(BaseModel):
    id: int
    nome: str
    email: str
    password: str
    permissao: str
    card_id: int

class LoginRequest(BaseModel):
    email: str
    password: str

class PasswordHashRequest(BaseModel):
    password: str
    card_id: int
    
class HashResetCodeRequest(BaseModel):
    code: str

class HashResetCodeRequest(BaseModel):
    code: str

class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str

class ResetCodeRequest(BaseModel):
    email: str
    card_id: int

class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyPasswordRequest(BaseModel):
    password: str
    hashed_password: str

class VerifyResetCodeRequest(BaseModel):
    submited_code: str
    reset_code: str

class VerifyToken(BaseModel):
    token: str

class CardComment(BaseModel):
    card_id: int
    text: str

class GetCardComment(BaseModel):
    card_id: int