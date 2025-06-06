from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Modelos Pydantic para validação de dados
class CourseUpdate(BaseModel):
    courseId: str
    status: Optional[str] = None
    observations: Optional[str] = None

class ConcorrenteIA(BaseModel):
    instituicao: str
    curso: str
    link: str
    valor: str

class DisciplinaIA(BaseModel):
    nome: str
    carga: int

class Coordenador(BaseModel):
    nome: str
    minibiografia: str
    jaECoordenador: bool

class Course(BaseModel):
    id: str
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
    status: Optional[str] = None
    observacoesComite: Optional[str] = None
    cargaHoraria: int

class ApiResponse(BaseModel):
    data: Optional[Dict[str, Any]] = None

# Modelos para requisições de login e token
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenRequest(BaseModel):
    token: str

class User(BaseModel):
    id: int
    nome: str
    email: str
    password: str
    permissao: str