from pydantic import BaseModel
from typing import List, Optional, Dict, Any

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
    nome: str
    coordenadorSolicitante: str
    coordenadores: List[Coordenador]
    apresentacao: str
    publico: str
    concorrentesIA: List[ConcorrenteIA]
    performance: str
    videoUrl: str
    disciplinasIA: List[DisciplinaIA]
    status: str
    observacoesComite: str

class ApiResponse(BaseModel):
    data: Optional[Dict[str, Any]] = None