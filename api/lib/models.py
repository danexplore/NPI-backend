from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Modelos Pydantic para validação de dados
class CourseUpdate(BaseModel):
    courseId: str
    status: str
    observations: Optional[str] = None

class ConcorrenteIA(BaseModel):
    instituicao: str
    curso: str
    link: str
    valor: str

class DisciplinaIA(BaseModel):
    nome: str
    carga: str

class Coordenador(BaseModel):
    nome: str
    minibiografia: str
    jaECoordenador: bool

class CourseUnyleya(BaseModel):
    id: str
    entity: str
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