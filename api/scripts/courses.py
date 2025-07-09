import os
from fastapi import HTTPException
import httpx
from typing import Dict
import json
import re
from ..lib.models import CourseUnyleya, CourseYMED, ApiResponse, CourseUpdate
import warnings
from dotenv import load_dotenv
from functools import reduce


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()

API_URL = "https://api.pipefy.com/graphql"
PIPEFY_API_KEY = os.getenv("PIPEFY_API_KEY")

if not PIPEFY_API_KEY:
    raise ValueError("PIPEFY_API_KEY não está definida nas variáveis de ambiente")

HEADERS = {
    "Authorization": f"Bearer {PIPEFY_API_KEY}",
    "Content-Type": "application/json",
}

def parse_api_response_unyleya(api_response: ApiResponse, phase_name: str) -> Dict[str, CourseUnyleya]:
    courses: Dict[str, CourseUnyleya] = {}

    edges = api_response.data.get("phase", {}).get("cards", {}).get("edges", [])

    def process_edge(edge):
        if not edge["node"]["id"] or not edge["node"]["fields"]:
            print(f"Estrutura de edge inválida: {json.dumps(edge)}")
            return None

        fields = edge["node"]["fields"]
        child_relations = edge["node"].get("child_relations", [])

        course = CourseUnyleya(
            id=edge["node"]["id"],
            entity="Unyleya",
            slug="",
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
            observacoesComite="",
            cargaHoraria=0,
            fase=phase_name
        )

        def process_field(course, field):
            if not field.get("name"):
                print(f"Estrutura de campo inválida: nome ausente {json.dumps(field)}")
                raise ValueError("Campo sem nome encontrado na resposta da API")

            value = field.get("native_value", "").strip() or ""

            if field["name"] == "curso-slug":
                course.slug = value.strip()
            if field["name"] == "Selecione o cadastro" or field.get("field", {}).get("id") == "nome_completo":
                if value:
                    course.coordenadorSolicitante = value.strip() if "[" not in value else value.split("[")[0].strip()

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
                    course.disciplinasIA = []
                    disciplinas = value.split("\n")

                    for disciplina in disciplinas:
                        valores = disciplina.split(";")
                        if len(valores) >= 1:
                            nome = valores[0]
                            carga = valores[1] if len(valores) > 1 else "0"
                            if len(valores) > 2:
                                tipo = "Reuso" if any(substring in valores[2].strip().lower() for substring in ["aproveitamento", "reaproveitamento", "reuso"]) else "Nova"
                            else:
                                tipo = "Não informado"
                        else:
                            nome = "Disciplina sem nome"
                            carga = "0"
                            tipo = "Não informado"
                            
                        try:
                            carga = re.search(r'\d+', carga).group()
                        except AttributeError:
                            carga = 0
                        course.disciplinasIA.append({
                            "nome": nome,
                            "carga": int(carga),
                            "tipo": tipo
                        })
                        course.cargaHoraria = sum(disciplina["carga"] for disciplina in course.disciplinasIA)

                    disciplinas_desenvolvimento = [
                        "Desenvolvimento Profissional".lower(),
                        "Desenvolvimento Pessoal e Profissional nas Carreiras da Saúde".lower()
                    ]
                    if not any(d["nome"].lower() in disciplinas_desenvolvimento for d in course.disciplinasIA):
                        course.disciplinasIA.insert(0, {
                            "nome": "Desenvolvimento Profissional",
                            "carga": 40,
                            "tipo": "Reuso"
                        })
                        course.cargaHoraria += 40
            elif field["name"] == "Status Pós-Comitê":
                course.status = value
            elif field["name"] == "Observações do Comitê":
                course.observacoesComite = value
            return course

        # Use reduce to process all fields
        course = reduce(process_field, fields, course)

        coordenador_nomes = [
            field["native_value"].strip() if "[" not in field["native_value"] else field["native_value"].split("[")[0].strip()
            for field in fields
            if field["name"].strip().startswith("Coordenador") and field.get("native_value")
        ]

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

        def build_coordenador(nome):
            if nome in coordenadores_info:
                return {
                    "nome": nome,
                    "minibiografia": coordenadores_info[nome]["minibiografia"],
                    "jaECoordenador": coordenadores_info[nome]["jaECoordenador"]
                }
            else:
                return {
                    "nome": nome,
                    "minibiografia": "",
                    "jaECoordenador": False
                }

        course.coordenadores = list(map(build_coordenador, coordenador_nomes))

        return (course.slug, course)

    # Use filter and dict to build the courses dictionary
    courses = dict(filter(lambda x: x is not None, map(process_edge, edges)))
    return courses

def parse_api_response_ymed(api_response: ApiResponse) -> Dict[str, CourseYMED]:
    courses = {}
    edges = api_response.data.get("phase", {}).get("cards", {}).get("edges", [])

    def get_slug(nome_do_curso: str):
        slug = nome_do_curso.lower()
        slug = re.sub(r'[áàãâ]', 'a', slug)
        slug = re.sub(r'[éê]', 'e', slug)
        slug = re.sub(r'[í]', 'i', slug)
        slug = re.sub(r'[óôõ]', 'o', slug)
        slug = re.sub(r'[ú]', 'u', slug)
        slug = re.sub(r'[ç]', 'c', slug)
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug

    def process_edge(edge):
        node = edge.get("node", {})
        fields = node.get("fields", [])
        field_map = {f.get("name"): f.get("native_value") for f in fields}
        benchmark_raw = field_map.get("Benchmark", "").strip().split("\n") if field_map.get("Benchmark") else []
        benchmark = json.loads(benchmark_raw[0]) if benchmark_raw else []

        course = CourseYMED(
            id=node.get("id"),
            entity="YMED",
            slug="",
            nomeDoCurso=field_map.get("Nome do Curso"),
            coordenador=field_map.get("Coordenador"),
            justificativaIntroducao=field_map.get("Justificativa/Introdução"),
            lacunaFormacaoGap=field_map.get("Lacuna de Formação (Gap)"),
            propostaCurso=field_map.get("Proposta do Curso"),
            publicoAlvo=field_map.get("Público-Alvo"),
            conteudoProgramatico=field_map.get("Conteúdo Programático"),
            mercado=field_map.get("Mercado"),
            diferencialCurso=field_map.get("Diferencial do Curso"),
            observacoesGerais=field_map.get("Observações Gerais"),
            status=field_map.get("Status Pós-Comitê") or "",
            observacoesComite=field_map.get("Observações do Comitê") or "",
            performance=field_map.get("Performance da Área") or "",
            concorrentes=benchmark or []
        )
        course.slug = get_slug(course.nomeDoCurso)
        return (course.slug, course)

    courses = dict(map(process_edge, edges))
    return courses

# Essa função busca os cursos pré-comitê do Pipefy
async def get_courses_pre_comite():
    QUERY = """
    {
    phase(id:"339377838") {
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
        return parse_api_response_unyleya(api_response, phase_name="precomite")
    
    except Exception as error:
        print(f"Erro ao buscar dados do Pipefy: {error}")
        raise HTTPException(status_code=500, detail="Falha ao buscar cursos")

async def get_courses_unyleya():
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
        return parse_api_response_unyleya(api_response, phase_name="comite")

    except Exception as error:
        print(f"Erro ao buscar dados do Pipefy: {error}")
        raise HTTPException(status_code=500, detail="Falha ao buscar cursos")

async def get_courses_ymed():
    QUERY = """
    {\n  phase(id: \"339017044\") {\n    cards_count\n    cards(first: 50) {\n      pageInfo {\n        hasNextPage\n        startCursor\n        endCursor\n      }\n      edges {\n        node {\n          id\n          fields {\n            name\n            native_value\n            field {\n              label\n              id\n            }\n          }\n        }\n      }\n    }\n  }\n}\n    """
    try:
        all_edges = []
        cursor = None
        has_next_page = True
        async with httpx.AsyncClient() as client:
            while has_next_page:
                paginated_query = QUERY
                if cursor:
                    paginated_query = QUERY.replace(
                        'cards(first: 50)', f'cards(first: 50, after: "{cursor}")'
                    )
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
        return parse_api_response_ymed(api_response)
    except Exception as error:
        print(f"Erro ao buscar dados do Pipefy: {error}")
        raise HTTPException(status_code=500, detail="Falha ao buscar cursos YMED")

async def update_course_status(course_update: CourseUpdate):
    UPDATE_CARD_FIELD_MUTATION = """
    mutation UpdateCardField($input: UpdateCardFieldInput!) {
        updateCardField(input: $input) {
            success
        }
    }
    """
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
            else:
                raise Exception("Selecione pelo menos um status")

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
        raise HTTPException(status_code=400, detail=f"Falha ao atualizar dados do curso. Error: {error}")

async def get_home_data():
    unyleya_courses_data = await get_courses_unyleya()
    ymed_courses_data = await get_courses_ymed()

    active_projects = len({"Unyleya", "YMED"})
    unyleya_proposals = len(unyleya_courses_data)
    ymed_proposals = len(ymed_courses_data)
    unyleya_coordinators = list(set([course.coordenadorSolicitante for course in unyleya_courses_data.values()]))
    ymed_coordinators = list(set([course.coordenador for course in ymed_courses_data.values() if course.coordenador]))
    coordinators = len(unyleya_coordinators) + len(ymed_coordinators)

    # Placeholder values for approved, pending, and rejected proposals
    approved_proposals = sum(1 for course in unyleya_courses_data.values() if course.status == "Aprovado") + \
                         sum(1 for course in ymed_courses_data.values() if course.status == "Aprovado")
    standby_proposals = sum(1 for course in unyleya_courses_data.values() if course.status == "Stand By") + \
                        sum(1 for course in ymed_courses_data.values() if course.status == "Stand By")
    rejected_proposals = sum(1 for course in unyleya_courses_data.values() if course.status == "Reprovado") + \
                         sum(1 for course in ymed_courses_data.values() if course.status == "Reprovado")
    pendent_proposals = sum(1 for course in unyleya_courses_data.values() if course.status == "") + \
                         sum(1 for course in ymed_courses_data.values() if course.status == "")
    
    result = ({
        "total_proposals": (unyleya_proposals + ymed_proposals),
        "active_projects": active_projects,
        "coordinators": coordinators,
        "unyleya_proposals": unyleya_proposals,
        "ymed_proposals": ymed_proposals,
        "coordinators": coordinators,
        "approved": approved_proposals,
        "standby": standby_proposals,
        "rejected": rejected_proposals,
        "pendent": pendent_proposals
    })

    return result

async def create_comment_in_card(card_id: str, text: str):
    if not card_id or not text:
        raise HTTPException(status_code=400, detail="Card ID e texto são obrigatórios")
    CREATE_COMMENT_MUTATION = """
    mutation CreateComment($input: CreateCommentInput!) {
        createComment(input: $input) {
            comment {
                id
                created_at
                text
            }
        }
    }
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_URL,
                headers=HEADERS,
                json={
                    "query": CREATE_COMMENT_MUTATION,
                    "variables": {
                        "input": {
                            "card_id": card_id,
                            "text": text
                        }
                    }
                }
            )
            data = response.json()
            if "errors" in data:
                raise Exception(data["errors"][0]["message"])
            return data["data"]["createComment"]["comment"]
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Falha ao criar comentário. Error: {error}")

async def get_card_comments_data(card_id: int):
    if not card_id:
        raise HTTPException(status_code=400, detail="Card ID é obrigatório")
    
    GET_COMMENTS_QUERY = """
    {
        card(id: %s) {
            comments {
                id
                text
                created_at
            }
        }
    }
    """ % card_id
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_URL,
                headers=HEADERS,
                json={
                    "query": GET_COMMENTS_QUERY,
                    "variables": {
                        "card_id": card_id
                    }
                }
            )
            data = response.json()
            if "errors" in data:
                raise Exception(data["errors"][0]["message"])
            return data["data"]["card"]["comments"]
        
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Falha ao buscar comentários. Error: {error}")