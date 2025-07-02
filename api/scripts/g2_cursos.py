import json
import os
from bs4 import BeautifulSoup
import pandas as pd
import re
import numpy as np
import unicodedata
from fastapi.responses import JSONResponse, FileResponse, Response
import pandas as pd
import time
from upstash_redis import Redis
from dotenv import load_dotenv
import orjson
import httpx

class ORJSONResponse(Response):
    media_type = "application/json"
    def render(self, content: any) -> bytes:
        return orjson.dumps(content)

load_dotenv()

redis = Redis.from_env()

def status_mapping(status):
    """Mapea o status para um valor legível."""
    status_map = {
        "Em construção": "Em construção",
        "Em Cadastro": "Em Cadastro",
        "Em oferta": "Em oferta",
        "Inativo": "Inativo"
    }
    return status_map.get(status, "Desconhecido")

def normalizar_nome(nome):
    # Remove espaços extras no início e fim
    if nome.startswith('Coord.'):
        nome = nome.replace('Coord.', 'Coordenação')
    nome = nome.strip()
    # Corrige espaços múltiplos internos
    nome = re.sub(r'\s+', ' ', nome)
    # Lista de preposições/conjunções a manter minúsculas
    preps = {"de", "da", "dos", "das", "e", "em"}
    maiusculas = {"AC"}

    # Garante que "em" fique minúsculo mesmo após title case
    nome = re.sub(r'\bEm\b', 'em', nome, flags=re.IGNORECASE)
    
    # Aplica Title Case e depois ajusta preposições/conjunções
    partes = nome.title().split()
    partes = [p.lower() if p.lower() in preps else p for p in partes]
    partes = [p.upper() if p in maiusculas else p for p in partes]
    # trnasforme "Coord." em "Coordenação"
    return ' '.join(partes)

def normalizar_titulo_exibicao(titulo):
    """
    Normaliza o título de exibição de forma semelhante ao modelo de normalizar_nome:
    - Remove parênteses e conteúdo dentro deles.
    - Remove espaços extras no início, fim e múltiplos internos.
    - Aplica Title Case.
    - Mantém preposições/conjunções em minúsculo.
    - Mantém siglas em maiúsculo.
    """
    if not isinstance(titulo, str):
        return titulo
    
    # Remove o prefixo "Pós-Graduação Lato Sensu em" (case insensitive)
    prefixes = ["Pós-Graduação Lato Sensu em", "Curso de Pós-Graduação Lato Sensu em ", "Lato Sensu Post-Graduation In "]
    for prefix in prefixes:
        if titulo.lower().startswith(prefix.lower()):
            titulo = titulo[len(prefix):]

    # Remove parênteses e conteúdo dentro deles
    titulo = re.sub(r'\(.*?\)', '', titulo)

    # Remove espaços extras no início e fim
    titulo = titulo.strip()
    # Corrige espaços múltiplos internos
    titulo = re.sub(r'\s+', ' ', titulo)

    # Lista de preposições/conjunções a manter minúsculas
    preps = {"ao", "à", "de", "da", "das", "do", "dos", "e", "em", "para", "com", "a", "o", "as", "os", "na", "no", "nas", "nos"}
    maiusculas = {"PPM", "LLM", "LL.M.", "CPA-20", "CPA20", "EFT", "TV", "SUS", "MBA", "ABA", "TCC", "ESG", "TOC", "CSI", "CSI:", "CPC", "LGBTQIAP+", "DTA", "DST", "II", "III", "SST", "UTI", "PMI", "TI", "EFPC", "BIM", "LGBTQIA+", "EAD", "CFP", "CFA", "ABECIP", "HIS", "CPA", "CGRPPS", "BPM", "BPMCBOK", "PMIPMBOK", "GRC", "CEA", "CGA", "CNPI", "QSMS", "RIG", "RH", "HIV/AIDS", "HIV", "AIDS", "ERP", "TDAH"}

    # Aplica Title Case
    partes = titulo.title().split()
    # Ajusta preposições/conjunções para minúsculo
    partes = [p.lower() if p.lower() in preps else p for p in partes]
    # Ajusta siglas para maiúsculo
    partes = [p.upper() if p.upper() in maiusculas else p for p in partes]

    return ' '.join(partes)

def titulo_para_slug(titulo):
    slug = unicodedata.normalize('NFKD', titulo)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    slug = slug.lower()
    slug = re.sub(r'\(.*?\)', '', slug)  # remove parênteses e conteúdo
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)  # remove caracteres especiais
    slug = re.sub(r'\s+', '-', slug)  # substitui espaços por hífens
    slug = re.sub(r'-+', '-', slug)  # evita múltiplos hífens
    slug = slug.strip('-')
    return slug

def corrigir_coordenador(nome):
    return normalizar_nome(nome)

async def get_dataframe():
    cache_key = "cursos_dataframe"
    cached_data = redis.get(cache_key)
    if cached_data:
        df = pd.DataFrame(json.loads(cached_data))
        print(df)
        return df
    url = "https://g2s.unyleya.com.br/projeto-pedagogico/gerar-xls/?st_descricao=1&st_projetopedagogico=1&st_coordenador=1&st_areaconhecimento=1"

    headers = {
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

    cookies = {
        "PHPSESSID": os.getenv("PHPSESSID")
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, cookies=cookies)
        print(f"Status Code: {response.status_code}")
        html = response.content

    soup = BeautifulSoup(html, 'html.parser')

    table = soup.find('table', {'id': 'table-ocorrencia-retorno'})

    def remove_illegal_characters(text):
        return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)

    headers_ = [remove_illegal_characters(header.text.strip()) for header in table.find_all('th')]

    rows = []
    for row in table.find_all('tr')[1:]:
        cells = row.find_all('td')
        cells = [remove_illegal_characters(cell.text.strip()) for cell in cells]
        rows.append(cells)

    # Converta os dados para um DataFrame
    df = pd.DataFrame(rows, columns=headers_)
    redis.set(cache_key, value=json.loads(df.to_json(orient='records')), nx=True, ex=60*30)
    return df

def map_status_academico(evolucao_academica):
    """
    Mapeia o status acadêmico para status simplificado de forma otimizada.
    
    Args:
        evolucao_academica: Status da evolução acadêmica
        
    Returns:
        str: Status mapeado (Ativo, Inativo, ou valor original)
    """
    if pd.isna(evolucao_academica):
        return "Inativo"
    
    status_mapping = {
        "Descontinuado": "Inativo",
        "Cancelado": "Inativo", 
        "Suspenso": "Inativo",
        "Em oferta": "Ativo"
    }
    
    return status_mapping.get(evolucao_academica, evolucao_academica)

async def transform_dataframe() -> pd.DataFrame:
    """
    Transforma o DataFrame de acordo com as regras especificadas.
    
    Melhorias implementadas:
    - Operações otimizadas com pandas para melhor performance
    - Uso de mapeamentos em lote ao invés de múltiplas operações individuais
    - Tratamento consolidado de valores nulos
    - Estrutura organizada e documentada
    
    Returns:
        pd.DataFrame: DataFrame transformado e limpo
    """
    df = await get_dataframe()
    df = df.copy()  # Evita warnings do pandas sobre modificações
    
    # ========== LIMPEZA E FORMATAÇÃO INICIAL ==========
    # Converte ID para inteiro removendo pontos
    df['ID'] = df['ID'].str.replace('.', '', regex=False).astype(int)
    
    # Adiciona data atual para status específicos sem data
    today = time.strftime('%d/%m/%Y')
    mask_add_date = (
        df['Evolução Acadêmica'].str.lower().isin(['em construção', 'em cadastro']) & 
        pd.isna(df['Data último status'])
    )
    df.loc[mask_add_date, 'Data último status'] = today
    
    # ========== MAPEAMENTOS OTIMIZADOS ==========
    # Mapeamento de versões do curso (operação em lote)
    version_mapping = {
        "SV40": "SV",
        "SV100": "SV", 
        "CV100": "CV"
    }
    df["Versão do Curso"] = df["Versão do Curso"].replace(version_mapping)
    
    # Mapeamento de segmentos por ID (operação otimizada)
    segment_mapping = {
        3621789: "Saúde",
        3621804: "Saúde", 
        3622914: "Saúde",
        3621732: "Outros",
        3622187: "Outros"
    }
    df["Segmento"] = df["ID"].map(segment_mapping).fillna(df["Segmento"])
    
    # ========== CORREÇÕES DE DADOS ==========
    # Correção de área de conhecimento
    df["Área de Conhecimento"] = df["Área de Conhecimento"].str.replace(
        "Saúde (não usar)", "Saúde", regex=False
    )
    
    # Filtragem de cursos de extensão
    df = df[df["Área de Conhecimento"] != "Cursos de Extensão"]
    
    # Tratamento de coordenadores vazios
    mask_empty_coord = df["Coordenador Titular"].isin(["\n", "", np.nan])
    df.loc[mask_empty_coord, "Coordenador Titular"] = "Não informado"
    df['Coordenador Titular'] = df['Coordenador Titular'].apply(corrigir_coordenador)
    
    # ========== MAPEAMENTO DE STATUS ==========
    # Aplicação otimizada do mapeamento de status
    df["Status"] = df["Evolução Acadêmica"].apply(map_status_academico)
    
    # ========== SELEÇÃO E ORDENAÇÃO DE COLUNAS ==========
    columns_order = [
        "ID", "Titulo de exibição", "Coordenador Titular", "Área de Conhecimento", 
        "Evolução Acadêmica", "Status", "Versão do Curso", "Segmento", 
        "Data último status", "Código eMEC", "Polo / Parceiro"
    ]
    df = df[columns_order]
    
    # ========== TRATAMENTO CONSOLIDADO DE VALORES NULOS ==========
    # Dicionário unificado para valores padrão
    default_values = {
        "Área de Conhecimento": "Não Informada",
        "Evolução Acadêmica": "Não Informado", 
        "Segmento": "Não Informado",
        "Versão do Curso": "Não Informada",  # Corrigido: era "Versão" 
        "Código eMEC": "Não Informado"
    }
    
    # Aplicação em lote dos valores padrão
    df = df.fillna(default_values)
    
    # ========== CRIAÇÃO DE COLUNAS DERIVADAS ==========
    # Normalização e slug em uma única passada
    df['Título Normalizado'] = df['Titulo de exibição'].apply(normalizar_titulo_exibicao)
    df['Slug'] = df['Título Normalizado'].apply(titulo_para_slug)
    
    return df

async def df_to_excel(file_name: str, sheet_name: str = 'PPs'):
    """
    Salva o DataFrame em um arquivo Excel.
    """
    df = await transform_dataframe()
    try:
        with pd.ExcelWriter(file_name) as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    except Exception as e:
        print(f"Erro ao salvar o arquivo Excel: {e}")

async def get_df_g2() -> pd.DataFrame:
    """
    Prepara o DataFrame para exportação ao Elastic.
    """
    df = await transform_dataframe()
    df_g2 = df[["ID", "Título Normalizado", "Coordenador Titular", "Área de Conhecimento", "Versão do Curso", "Evolução Acadêmica", "Status", "Segmento", "Slug", "Código eMEC"]].copy()
    columns = {
        'ID': 'ID',
        'Título Normalizado': 'Título',
        'Coordenador Titular': 'Coordenador',
        'Área de Conhecimento': 'Área de Conhecimento',
        'Versão do Curso': 'Versão',
        'Evolução Acadêmica': 'Status Acadêmico',
        'Status': 'Status',
        'Segmento': 'Segmento',
        'Slug': 'Slug',
        'Código eMEC': 'Código eMEC'
    }
    df_g2.rename(columns=columns, inplace=True)
    return df_g2

async def get_df_search() -> pd.DataFrame:
    """
    Prepara o DataFrame para exportação ao Elastic.
    """
    df = await transform_dataframe()
    df_search = df[["ID", "Título Normalizado", "Status"]].copy()
    columns = {
        'ID': 'ID',
        'Título Normalizado': 'Título'
    }
    df_search.rename(columns=columns, inplace=True)
    df_search["Sistema"] = "G2"
    return df_search

async def save_df_g2():
    """
    Salva o DataFrame preparado para o G2 em arquivos Excel e CSV.
    """
    df_elastic = await get_df_g2()
    df_elastic.to_excel("Cursos G2.xlsx", index=False, sheet_name='Cursos G2')
    df_elastic.to_csv("Cursos G2.csv", index=False, encoding='utf-8')

async def get_cursos_g2():
    cache_key = "cursos_g2_data"
    cached_data = redis.get(cache_key)
    if cached_data:
        data = json.loads(cached_data)
        return JSONResponse(content=data, media_type="application/json", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})
    df = await get_df_g2()
    data = df.to_dict(orient="records")
    redis.set(cache_key, value=json.loads(df.to_json(orient='records')), nx=True, ex=60*30)
    return JSONResponse(content=data, media_type="application/json", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})

async def get_cursos_g2_excel():
    df = await get_df_g2()
    excel_file = "Cursos G2.xlsx"
    df.to_excel(excel_file, index=False, sheet_name='Cursos G2')
    return FileResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Cursos G2.xlsx"
    )

async def get_cursos_search():
    cache_key = "cursos_search_data"
    cached_data = redis.get(cache_key)
    if cached_data:
        data = json.loads(cached_data)
        return JSONResponse(content=data, media_type="application/json", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})
    df = await get_df_search()
    data = df.to_dict(orient="records")
    redis.set(cache_key, value=json.loads(df.to_json(orient='records')), nx=True, ex=60*30)
    return JSONResponse(content=data, media_type="application/json", headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "Content-Type"})

async def refresh_cursos_g2():
    redis.delete("cursos_g2_data", "cursos_search_data")
    await get_cursos_g2()
    await get_cursos_search()
    return {"message": "Cursos G2 e Search atualizados com sucesso."}