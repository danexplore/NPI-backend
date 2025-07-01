"""
Módulo para processamento e transformação de dados de cursos do sistema G2.

Este módulo contém funções para:
- Extrair dados de cursos via web scraping
- Transformar e normalizar dados
- Gerar exports em diferentes formatos
- Gerenciar cache com Redis
"""

import json
import os
import re
import time
import unicodedata
from typing import Dict, List, Optional, Any

import httpx
import numpy as np
import orjson
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi.responses import JSONResponse, FileResponse, Response
from upstash_redis import Redis

# ========== CONFIGURAÇÃO INICIAL ==========
load_dotenv()
redis = Redis.from_env()

# ========== CONSTANTES ==========
CACHE_EXPIRATION = 60 * 30  # 30 minutos
DEFAULT_SHEET_NAME = 'PPs'

# Mapeamentos para normalização
VERSION_MAPPING = {
    'SV40': 'SV',
    'SV100': 'SV',
    'CV100': 'CV'
}

SEGMENT_IDS = {
    'Saúde': [3621789, 3621804, 3622914],
    'Outros': [3621732, 3622187]
}

STATUS_MAPPING = {
    'Descontinuado': 'Inativo',
    'Cancelado': 'Inativo',
    'Suspenso': 'Inativo',
    'Em oferta': 'Ativo'
}

DEFAULT_VALUES = {
    'Área de Conhecimento': 'Não Informada',
    'Evolução Acadêmica': 'Não Informado',
    'Segmento': 'Não Informado',
    'Versão do Curso': 'Não Informada',
    'Código eMEC': 'Não Informado',
    'Coordenador Titular': 'Não informado'
}

# Listas para normalização de títulos
PREPOSITIONS = {
    "ao", "à", "de", "da", "das", "do", "dos", "e", "em", "para", 
    "com", "a", "o", "as", "os", "na", "no", "nas", "nos"
}

ACRONYMS = {
    "PPM", "LLM", "LL.M.", "CPA-20", "CPA20", "EFT", "TV", "SUS", "MBA", 
    "ABA", "TCC", "ESG", "TOC", "CSI", "CSI:", "CPC", "LGBTQIAP+", "DTA", 
    "DST", "II", "III", "SST", "UTI", "PMI", "TI", "EFPC", "BIM", 
    "LGBTQIA+", "EAD", "CFP", "CFA", "ABECIP", "HIS", "CPA", "CGRPPS", 
    "BPM", "BPMCBOK", "PMIPMBOK", "GRC", "CEA", "CGA", "CNPI", "QSMS", 
    "RIG", "RH", "HIV/AIDS", "HIV", "AIDS", "ERP", "TDAH"
}

TITLE_PREFIXES_TO_REMOVE = [
    "Pós-Graduação Lato Sensu em",
    "Curso de Pós-Graduação Lato Sensu em ",
    "Lato Sensu Post-Graduation In "
]

# Headers para requisições HTTP
REQUEST_HEADERS = {
    "authority": "g2s.unyleya.com.br",
    "method": "GET",
    "scheme": "https",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
}


class ORJSONResponse(Response):
    """Resposta otimizada usando orjson para melhor performance."""
    media_type = "application/json"
    
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)

# ========== FUNÇÕES UTILITÁRIAS ==========

def remove_illegal_characters(text: str) -> str:
    """Remove caracteres ilegais de strings extraídas do HTML."""
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)


def normalize_text_basic(text: str) -> str:
    """Normalização básica de texto: remove espaços extras e aplica strip."""
    if not isinstance(text, str):
        return text
    return re.sub(r'\s+', ' ', text.strip())


def normalize_name(nome: str) -> str:
    """
    Normaliza nomes de coordenadores aplicando regras específicas.
    
    Args:
        nome: Nome a ser normalizado
        
    Returns:
        Nome normalizado seguindo as regras de formatação
    """
    if not isinstance(nome, str) or not nome.strip():
        return DEFAULT_VALUES['Coordenador Titular']
    
    # Substitui abreviações
    if nome.startswith('Coord.'):
        nome = nome.replace('Coord.', 'Coordenação', 1)
    
    # Normalização básica
    nome = normalize_text_basic(nome)
    
    # Aplica Title Case e ajusta preposições
    nome_preps = {"de", "da", "dos", "das", "e", "em"}
    nome_maiusculas = {"AC"}
    
    # Garante que "em" fique minúsculo
    nome = re.sub(r'\bEm\b', 'em', nome, flags=re.IGNORECASE)
    
    # Aplica formatação
    partes = nome.title().split()
    partes = [
        p.upper() if p in nome_maiusculas
        else p.lower() if p.lower() in nome_preps
        else p
        for p in partes
    ]
    
    return ' '.join(partes)


def normalize_course_title(titulo: str) -> str:
    """
    Normaliza títulos de cursos removendo prefixos e aplicando formatação.
    
    Args:
        titulo: Título do curso a ser normalizado
        
    Returns:
        Título normalizado
    """
    if not isinstance(titulo, str):
        return titulo
    
    # Remove prefixos conhecidos
    for prefix in TITLE_PREFIXES_TO_REMOVE:
        if titulo.lower().startswith(prefix.lower()):
            titulo = titulo[len(prefix):].strip()
            break
    
    # Remove parênteses e conteúdo
    titulo = re.sub(r'\(.*?\)', '', titulo)
    
    # Normalização básica
    titulo = normalize_text_basic(titulo)
    
    # Aplica Title Case com ajustes
    partes = titulo.title().split()
    partes = [
        p.upper() if p.upper() in ACRONYMS
        else p.lower() if p.lower() in PREPOSITIONS
        else p
        for p in partes
    ]
    
    return ' '.join(partes)


def title_to_slug(titulo: str) -> str:
    """
    Converte título em slug URL-friendly.
    
    Args:
        titulo: Título a ser convertido
        
    Returns:
        Slug gerado
    """
    if not isinstance(titulo, str):
        return ""
    
    # Normaliza unicode e remove acentos
    slug = unicodedata.normalize('NFKD', titulo)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    slug = slug.lower()
    
    # Remove parênteses e caracteres especiais
    slug = re.sub(r'\(.*?\)', '', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    
    return slug.strip('-')


def map_academic_status_to_status(evolucao: Any) -> str:
    """
    Mapeia evolução acadêmica para status do sistema.
    
    Args:
        evolucao: Valor da evolução acadêmica
        
    Returns:
        Status mapeado
    """
    if pd.isna(evolucao):
        return 'Inativo'
    
    return STATUS_MAPPING.get(evolucao, evolucao)


def create_segment_mapping() -> Dict[int, str]:
    """Cria dicionário de mapeamento ID -> Segmento."""
    mapping = {}
    for segment, ids in SEGMENT_IDS.items():
        mapping.update({id_: segment for id_ in ids})
    return mapping


def get_current_date() -> str:
    """Retorna a data atual formatada."""
    return time.strftime('%d/%m/%Y')

async def get_dataframe() -> pd.DataFrame:
    """
    Extrai dados da tabela HTML e retorna um DataFrame.
    Utiliza cache Redis para otimizar performance.
    
    Returns:
        DataFrame com os dados dos cursos
    """
    cache_key = "cursos_dataframe"
    
    # Verifica cache primeiro
    cached_data = redis.get(cache_key)
    if cached_data:
        df = pd.DataFrame(json.loads(cached_data))
        print(f"[CACHE] DataFrame carregado do cache com {len(df)} registros")
        return df
    
    # URL para extração de dados
    url = ("https://g2s.unyleya.com.br/projeto-pedagogico/gerar-xls/"
           "?st_descricao=1&st_projetopedagogico=1&st_coordenador=1&st_areaconhecimento=1")
    
    cookies = {"PHPSESSID": os.getenv("PHPSESSID")}
    
    try:
        # Faz requisição HTTP
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=REQUEST_HEADERS, cookies=cookies)
            response.raise_for_status()
            print(f"[HTTP] Status Code: {response.status_code}")
            
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'id': 'table-ocorrencia-retorno'})
        
        if not table:
            raise ValueError("Tabela não encontrada no HTML")
        
        # Extrai headers
        headers = [
            remove_illegal_characters(header.text.strip()) 
            for header in table.find_all('th')
        ]
        
        # Extrai dados das linhas
        rows = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = [
                remove_illegal_characters(cell.text.strip()) 
                for cell in row.find_all('td')
            ]
            if cells:  # Só adiciona se não estiver vazia
                rows.append(cells)
        
        # Cria DataFrame
        df = pd.DataFrame(rows, columns=headers)
        print(f"[DATA] DataFrame criado com {len(df)} registros e {len(headers)} colunas")
        
        # Armazena no cache
        cache_data = json.loads(df.to_json(orient='records'))
        redis.set(cache_key, value=cache_data, nx=True, ex=CACHE_EXPIRATION)
        print(f"[CACHE] Dados armazenados no cache por {CACHE_EXPIRATION//60} minutos")
        
        return df
        
    except Exception as e:
        print(f"[ERROR] Erro ao extrair dados: {e}")
        raise

async def transform_dataframe() -> pd.DataFrame:
    """
    Transforma o DataFrame de acordo com as regras especificadas.
    Aplica normalizações, correções de dados e cria colunas derivadas.
    """
    df = await get_dataframe()
    
    # ========== LIMPEZA E CONVERSÃO DE TIPOS ==========
    # Converte ID para inteiro removendo pontos
    df['ID'] = df['ID'].str.replace('.', '', regex=False).astype(int)
    
    # ========== MAPEAMENTOS DE VERSÃO DO CURSO ==========
    # Usa replace para melhor performance em operações múltiplas
    df['Versão do Curso'] = df['Versão do Curso'].replace(VERSION_MAPPING)
    
    # ========== MAPEAMENTOS DE SEGMENTO POR ID ==========
    # Define mapeamentos de segmento para IDs específicos
    segment_mapping = create_segment_mapping()
    df['Segmento'] = df['ID'].map(segment_mapping).fillna(df['Segmento'])
    
    # ========== CORREÇÕES DE ÁREA DE CONHECIMENTO ==========
    df['Área de Conhecimento'] = df['Área de Conhecimento'].str.replace(
        'Saúde (não usar)', 'Saúde', regex=False
    )
    # Filtra cursos de extensão
    df = df[df['Área de Conhecimento'] != 'Cursos de Extensão'].copy()
    
    # ========== CORREÇÃO DE STATUS BASEADO EM EVOLUÇÃO ACADÊMICA ==========
    df['Status'] = df['Evolução Acadêmica'].apply(map_academic_status_to_status)
    
    # ========== ADIÇÃO DE DATA PARA STATUS EM CONSTRUÇÃO/CADASTRO ==========
    # Adiciona data atual para cursos em construção/cadastro sem data
    today = get_current_date()
    mask_add_date = (
        df['Evolução Acadêmica'].str.lower().isin(['em construção', 'em cadastro']) & 
        df['Data último status'].isna()
    )
    df.loc[mask_add_date, 'Data último status'] = today
    
    # ========== SELEÇÃO E REORDENAÇÃO DE COLUNAS ==========
    columns_order = [
        'ID', 'Titulo de exibição', 'Coordenador Titular', 'Área de Conhecimento',
        'Evolução Acadêmica', 'Status', 'Versão do Curso', 'Segmento',
        'Data último status', 'Código eMEC', 'Polo / Parceiro'
    ]
    df = df[columns_order].copy()
    
    # ========== TRATAMENTO DE VALORES NULOS/VAZIOS ==========
    # Aplica valores padrão para colunas nulas
    df = df.fillna(DEFAULT_VALUES)
    
    # Tratamento especial para Coordenador Titular (inclui strings vazias e quebras de linha)
    df['Coordenador Titular'] = df['Coordenador Titular'].apply(normalize_name)
    
    # ========== CRIAÇÃO DE COLUNAS DERIVADAS ==========
    # Aplica normalização de títulos e criação de slugs
    df['Título Normalizado'] = df['Titulo de exibição'].apply(normalize_course_title)
    df['Slug'] = df['Título Normalizado'].apply(title_to_slug)
    
    return df

# ========== FUNÇÕES DE EXPORTAÇÃO E PROCESSAMENTO ==========

async def save_dataframe_to_excel(file_name: str, sheet_name: str = DEFAULT_SHEET_NAME) -> None:
    """
    Salva o DataFrame transformado em um arquivo Excel.
    
    Args:
        file_name: Nome do arquivo a ser criado
        sheet_name: Nome da planilha (padrão: 'PPs')
    """
    try:
        df = await transform_dataframe()
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"[EXPORT] Arquivo Excel salvo: {file_name}")
    except Exception as e:
        print(f"[ERROR] Erro ao salvar arquivo Excel: {e}")
        raise


async def get_g2_formatted_dataframe() -> pd.DataFrame:
    """
    Prepara o DataFrame para exportação com colunas específicas do G2.
    
    Returns:
        DataFrame formatado para o sistema G2
    """
    df = await transform_dataframe()
    
    # Seleciona e renomeia colunas para o formato G2
    g2_columns = [
        "ID", "Título Normalizado", "Coordenador Titular", "Área de Conhecimento", 
        "Versão do Curso", "Evolução Acadêmica", "Status", "Segmento", "Slug", "Código eMEC"
    ]
    
    df_g2 = df[g2_columns].copy()
    
    # Renomeia colunas para padrão G2
    column_mapping = {
        'Título Normalizado': 'Título',
        'Coordenador Titular': 'Coordenador',
        'Versão do Curso': 'Versão',
        'Evolução Acadêmica': 'Status Acadêmico'
    }
    
    df_g2.rename(columns=column_mapping, inplace=True)
    return df_g2


async def get_search_formatted_dataframe() -> pd.DataFrame:
    """
    Prepara o DataFrame para exportação no formato de busca.
    
    Returns:
        DataFrame formatado para sistema de busca
    """
    df = await transform_dataframe()
    
    # Seleciona colunas para busca
    search_columns = ["ID", "Título Normalizado", "Status"]
    df_search = df[search_columns].copy()
    
    # Renomeia e adiciona coluna do sistema
    df_search.rename(columns={'Título Normalizado': 'Título'}, inplace=True)
    df_search["Sistema"] = "G2"
    
    return df_search


async def save_g2_exports() -> Dict[str, str]:
    """
    Salva arquivos de exportação do G2 em Excel e CSV.
    
    Returns:
        Dicionário com status das exportações
    """
    try:
        df_g2 = await get_g2_formatted_dataframe()
        
        # Salva Excel
        excel_file = "Cursos G2.xlsx"
        df_g2.to_excel(excel_file, index=False, sheet_name='Cursos G2')
        
        # Salva CSV
        csv_file = "Cursos G2.csv"
        df_g2.to_csv(csv_file, index=False, encoding='utf-8')
        
        return {
            "excel": f"Arquivo salvo: {excel_file}",
            "csv": f"Arquivo salvo: {csv_file}",
            "records": len(df_g2)
        }
    except Exception as e:
        print(f"[ERROR] Erro ao salvar exports G2: {e}")
        raise

# ========== FUNÇÕES DE API ==========

def create_cors_headers() -> Dict[str, str]:
    """Cria headers CORS padrão para as respostas da API."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }


async def get_g2_courses_api() -> JSONResponse:
    """
    Endpoint da API para obter cursos G2 em formato JSON.
    Utiliza cache Redis para otimizar performance.
    
    Returns:
        JSONResponse com dados dos cursos G2
    """
    cache_key = "cursos_g2_data"
    
    try:
        # Verifica cache primeiro
        cached_data = redis.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            print(f"[API] Dados G2 retornados do cache: {len(data)} registros")
            return JSONResponse(
                content=data,
                media_type="application/json",
                headers=create_cors_headers()
            )
        
        # Busca dados frescos
        df = await get_g2_formatted_dataframe()
        data = df.to_dict(orient="records")
        
        # Armazena no cache
        cache_data = json.loads(df.to_json(orient='records'))
        redis.set(cache_key, value=cache_data, nx=True, ex=CACHE_EXPIRATION)
        
        print(f"[API] Dados G2 processados: {len(data)} registros")
        return JSONResponse(
            content=data,
            media_type="application/json",
            headers=create_cors_headers()
        )
        
    except Exception as e:
        print(f"[ERROR] Erro na API G2: {e}")
        return JSONResponse(
            content={"error": "Erro interno do servidor"},
            status_code=500,
            headers=create_cors_headers()
        )


async def get_g2_courses_excel() -> FileResponse:
    """
    Endpoint da API para download de cursos G2 em formato Excel.
    
    Returns:
        FileResponse com arquivo Excel
    """
    try:
        df = await get_g2_formatted_dataframe()
        excel_file = "Cursos G2.xlsx"
        df.to_excel(excel_file, index=False, sheet_name='Cursos G2')
        
        print(f"[API] Arquivo Excel G2 gerado: {len(df)} registros")
        return FileResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="Cursos G2.xlsx"
        )
    except Exception as e:
        print(f"[ERROR] Erro ao gerar Excel G2: {e}")
        raise


async def get_search_courses_api() -> JSONResponse:
    """
    Endpoint da API para obter cursos formatados para busca.
    Utiliza cache Redis para otimizar performance.
    
    Returns:
        JSONResponse com dados dos cursos para busca
    """
    cache_key = "cursos_search_data"
    
    try:
        # Verifica cache primeiro
        cached_data = redis.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            print(f"[API] Dados Search retornados do cache: {len(data)} registros")
            return JSONResponse(
                content=data,
                media_type="application/json",
                headers=create_cors_headers()
            )
        
        # Busca dados frescos
        df = await get_search_formatted_dataframe()
        data = df.to_dict(orient="records")
        
        # Armazena no cache
        cache_data = json.loads(df.to_json(orient='records'))
        redis.set(cache_key, value=cache_data, nx=True, ex=CACHE_EXPIRATION)
        
        print(f"[API] Dados Search processados: {len(data)} registros")
        return JSONResponse(
            content=data,
            media_type="application/json",
            headers=create_cors_headers()
        )
        
    except Exception as e:
        print(f"[ERROR] Erro na API Search: {e}")
        return JSONResponse(
            content={"error": "Erro interno do servidor"},
            status_code=500,
            headers=create_cors_headers()
        )


async def refresh_all_caches() -> Dict[str, Any]:
    """
    Limpa todos os caches e recarrega os dados.
    
    Returns:
        Status da operação de refresh
    """
    try:
        # Limpa caches
        cache_keys = ["cursos_g2_data", "cursos_search_data", "cursos_dataframe"]
        deleted_count = redis.delete(*cache_keys)
        
        # Recarrega dados
        await get_g2_courses_api()
        await get_search_courses_api()
        
        print(f"[CACHE] Refresh completo: {deleted_count} caches limpos")
        return {
            "message": "Caches atualizados com sucesso",
            "caches_cleared": deleted_count,
            "timestamp": get_current_date()
        }
        
    except Exception as e:
        print(f"[ERROR] Erro no refresh: {e}")
        return {
            "error": "Erro ao atualizar caches",
            "timestamp": get_current_date()
        }


# ========== FUNÇÕES LEGADAS (COMPATIBILIDADE) ==========
# Mantém compatibilidade com código existente

async def get_df_g2() -> pd.DataFrame:
    """Função legada - use get_g2_formatted_dataframe()"""
    return await get_g2_formatted_dataframe()


async def get_df_search() -> pd.DataFrame:
    """Função legada - use get_search_formatted_dataframe()"""
    return await get_search_formatted_dataframe()


async def get_cursos_g2():
    """Função legada - use get_g2_courses_api()"""
    return await get_g2_courses_api()


async def get_cursos_g2_excel():
    """Função legada - use get_g2_courses_excel()"""
    return await get_g2_courses_excel()


async def get_cursos_search():
    """Função legada - use get_search_courses_api()"""
    return await get_search_courses_api()


async def refresh_cursos_g2():
    """Função legada - use refresh_all_caches()"""
    result = await refresh_all_caches()
    return {"message": "Cursos G2 e Search atualizados com sucesso."}