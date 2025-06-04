from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
from typing import Dict
import json
from .models import Course, ApiResponse, CourseUpdate
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from redis import asyncio as aioredis

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas as origens
    allow_methods=["*"],
    allow_headers=["*"],
)

API_URL = "https://api.pipefy.com/graphql"
PIPEFY_API_KEY = os.getenv("PIPEFY_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

if not PIPEFY_API_KEY:
    raise ValueError("PIPEFY_API_KEY não está definida nas variáveis de ambiente")

if not REDIS_URL:
    raise ValueError("REDIS_URL não está definida nas variáveis de ambiente")

HEADERS = {
    "Authorization": f"Bearer {PIPEFY_API_KEY}",
    "Content-Type": "application/json",
}

QUERY = """
{
  phase(id:"333225221") {
    cards (first: 50) {
      edges {
        node {
          id
          fields {
            name
            native_value
            field {
              label
              id
            }
          }
          child_relations {
            __typename
            cards {
              fields {
                name
                value
              }
            }
          }
        }
      }
      pageInfo {
        hasNextPage
        startCursor
        endCursor
      }
    }
  }
}
"""

def parse_api_response(api_response: ApiResponse) -> Dict[str, Course]:
    courses: Dict[str, Course] = {}
    
    edges = api_response.data.get("phase", {}).get("cards", {}).get("edges", [])
    for edge in edges:
        if not edge["node"]["id"] or not edge["node"]["fields"]:
            print(f"Estrutura de edge inválida: {json.dumps(edge)}")
            continue

        fields = edge["node"]["fields"]
        child_relations = edge["node"].get("child_relations", [])

        # Inicializa o objeto do curso
        course = Course(
            id=edge["node"]["id"],
            nome="",
            coordenadorSolicitante="Sem coordenador",
            coordenadores=[],
            apresentacao="",
            publico="",
            concorrentesIA=[],
            performance="",
            videoUrl="",
            disciplinasIA=[],
            status="",
            observacoesComite=""
        )

        # Processa os campos principais
        for field in fields:
            if not field.get("name"):
                print(f"Estrutura de campo inválida: nome ausente {json.dumps(field)}")
                continue

            value = field.get("native_value", "").strip() or ""

            # Verifica se é um dos campos de coordenador solicitante
            if field["name"] == "Selecione o cadastro" or field.get("field", {}).get("id") == "nome_completo":
                if value:
                    course.coordenadorSolicitante = value

            if field["name"] == "Nome do Curso":
                if "[" in value:
                    course.nome = value.split("[")[0].strip()
                else:
                    course.nome = value.strip()
            elif field["name"] == "Apresentação IA":
                course.apresentacao = value
            elif field["name"] == "Público Alvo IA":
                course.publico = value
            elif field["name"] == "Concorrentes IA":
                if value:
                    try:
                        formatted_value = value.strip()
                        if not (formatted_value.startswith("[") and formatted_value.endswith("]")):
                            raise ValueError("Formato JSON inválido para Concorrentes IA")
                        
                        formatted_value = formatted_value.replace(",\n]", "]")
                        parsed_value = json.loads(formatted_value)
                        
                        if isinstance(parsed_value, str):
                            parsed_value = json.loads(parsed_value)
                        
                        if isinstance(parsed_value, list):
                            course.concorrentesIA = [
                                {
                                    "instituicao": str(item.split(";")[0].strip()),
                                    "curso": str(f"{item.split(';')[1].strip()} - {item.split(';')[2].strip()}"),
                                    "link": str(item.split(";")[3].strip()),
                                    "valor": str(item.split(";")[4].strip()) if len(item.split(";")) > 4 else "Valor desconhecido"
                                }
                                for item in parsed_value
                            ]
                        else:
                            raise ValueError("Valor analisado não é uma lista")
                    except Exception as error:
                        print(f"Erro ao analisar Concorrentes IA: {error}")
                        course.concorrentesIA = [{
                            "instituicao": "Erro ao processar",
                            "curso": "Erro ao processar",
                            "link": "#",
                            "valor": "Erro ao processar"
                        }]
            elif field["name"] == "Performance de Cursos / Área correlatas":
                course.performance = value
            elif field["name"] == "Vídeo de Defesa da Proposta de Curso":
                course.videoUrl = value
            elif field["name"] == "Disciplinas IA":
                if value:
                    values = value.split(";")
                    nome = values[0]
                    carga = values[1] if " " not in values[1] else values[1].split(" ")[0]
                    course.disciplinasIA = {"nome": nome, "carga": carga}
            elif field["name"] == "Status Pós-Comitê":
                course.status = value
            elif field["name"] == "Observações do comitê":
                course.observacoesComite = value

        # Coleta nomes dos coordenadores
        coordenador_nomes = []
        for field in fields:
            if field["name"].strip().startswith("Coordenador") and field.get("native_value"):
                coordenador_nomes.append(field["native_value"].strip())

        # Busca informações detalhadas dos coordenadores
        coordenadores_info = {}
        for relation in child_relations:
            if relation.get("cards"):
                coord_card = relation["cards"][0]
                coord_fields = coord_card["fields"]

                nome_field = next((f for f in coord_fields if f.get("name", "").lower() == "nome completo"), None)
                if not nome_field or not nome_field.get("value"):
                    continue

                nome = nome_field["value"].strip()
                minibiografia = next((f["value"] for f in coord_fields if f.get("name") == "Minibiografia"), "")
                ja_e_coordenador = next((f["value"] == "Sim" for f in coord_fields if f.get("name") == "Já é coordenador da Unyleya?"), False)

                coordenadores_info[nome] = {
                    "minibiografia": minibiografia,
                    "jaECoordenador": ja_e_coordenador
                }

        # Cria lista final de coordenadores
        for nome in coordenador_nomes:
            if nome in coordenadores_info:
                course.coordenadores.append({
                    "nome": nome,
                    "minibiografia": coordenadores_info[nome]["minibiografia"],
                    "jaECoordenador": coordenadores_info[nome]["jaECoordenador"]
                })
            else:
                course.coordenadores.append({
                    "nome": nome,
                    "minibiografia": "",
                    "jaECoordenador": False
                })

        courses[course.id] = course

    return courses

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url(REDIS_URL, encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

@app.get("/")
async def root():
    return {"message": "API de Cursos da Unyleya - Versão 1.0"}

@app.get("/courses")
@cache(expire=300)  # Cache por 5 minutos
async def get_courses():
    try:
        all_edges = []
        cursor = None
        has_next_page = True

        async with httpx.AsyncClient() as client:
            while has_next_page:
                paginated_query = QUERY
                if cursor:
                    paginated_query = QUERY.replace(
                        'cards (first: 50)', f'cards (first: 50, after: "{cursor}")'
                    )
                else:
                    paginated_query = QUERY

                response = await client.post(
                    API_URL,
                    headers=HEADERS,
                    json={"query": paginated_query}
                )

                if not response.is_success:
                    raise HTTPException(status_code=response.status_code, detail="Erro na requisição ao Pipefy")

                payload = response.json().get("data", {}).get("phase", {}).get("cards", {})
                edges = payload.get("edges", [])
                page_info = payload.get("pageInfo", {})
                all_edges.extend(edges)

                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
        
        nested_data = {
            "phase": {
                "cards": {
                    "edges": all_edges
                }
            }
        }
        api_response = ApiResponse(data=nested_data)
        return parse_api_response(api_response)

    except Exception as error:
        print(f"Erro ao buscar dados do Pipefy: {error}")
        raise HTTPException(status_code=500, detail="Falha ao buscar cursos")

UPDATE_CARD_FIELD_MUTATION = """
mutation UpdateCardField($input: UpdateCardFieldInput!) {
    updateCardField(input: $input) {
        success
    }
}
"""

@app.post("/update-course-status")
async def update_course_status(course_update: CourseUpdate):
    if not course_update.courseId:
        raise HTTPException(status_code=400, detail="Course ID é obrigatório")

    try:
        async with httpx.AsyncClient() as client:
            # Atualizar status se fornecido
            if course_update.status:
                status_response = await client.post(
                    API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {PIPEFY_API_KEY}",
                    },
                    json={
                        "query": UPDATE_CARD_FIELD_MUTATION,
                        "variables": {
                            "input": {
                                "card_id": course_update.courseId,
                                "field_id": "status_p_s_comit",
                                "new_value": course_update.status,
                            }
                        },
                    },
                )
                status_data = status_response.json()
                if "errors" in status_data:
                    raise Exception(status_data["errors"][0]["message"])

            # Atualizar observações se fornecidas
            if course_update.observations is not None:
                observations_response = await client.post(
                    API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {PIPEFY_API_KEY}",
                    },
                    json={
                        "query": UPDATE_CARD_FIELD_MUTATION,
                        "variables": {
                            "input": {
                                "card_id": course_update.courseId,
                                "field_id": "observa_es_do_comit",
                                "new_value": course_update.observations,
                            }
                        },
                    },
                )
                observations_data = observations_response.json()
                if "errors" in observations_data:
                    raise Exception(observations_data["errors"][0]["message"])

        return {
            "success": True,
            "status": course_update.status,
            "observations": course_update.observations,
        }

    except Exception as error:
        print(f"Erro ao atualizar dados do curso: {error}")
        raise HTTPException(status_code=500, detail="Falha ao atualizar dados do curso")