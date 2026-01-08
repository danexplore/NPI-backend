#!/usr/bin/env python3
"""
Script de diagnóstico para verificar a saúde do backend NPI
Testa conexão com Pipefy, Redis e variáveis de ambiente
"""

import os
import sys
import asyncio
import httpx
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def check_env_vars():
    """Verifica se todas as variáveis de ambiente necessárias estão definidas"""
    print("=" * 60)
    print("VERIFICANDO VARIÁVEIS DE AMBIENTE")
    print("=" * 60)
    
    required_vars = [
        "PIPEFY_API_KEY",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "OPENAI_API_KEY",
        "BASIC_AUTH_USERS"
    ]
    
    for var in required_vars:
        value = os.getenv(var)
        status = "✓ OK" if value else "✗ FALTANDO"
        # Ocultar valores sensíveis
        display_value = f"{value[:20]}..." if value and len(value) > 20 else value
        print(f"{var}: {status} ({display_value})")
    
    print()

def check_pipefy_connection():
    """Testa a conexão com API Pipefy"""
    print("=" * 60)
    print("VERIFICANDO CONEXÃO COM PIPEFY")
    print("=" * 60)
    
    pipefy_key = os.getenv("PIPEFY_API_KEY")
    if not pipefy_key:
        print("✗ PIPEFY_API_KEY não definida")
        return False
    
    try:
        # Fazer uma query simples
        headers = {
            "Authorization": f"Bearer {pipefy_key}",
            "Content-Type": "application/json",
        }
        
        # Query para testar conexão sem fase específica
        test_query = '{ me { name email } }'
        
        response = httpx.post(
            "https://api.pipefy.com/graphql",
            headers=headers,
            json={"query": test_query},
            timeout=10.0
        )
        
        print(f"Status HTTP: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                print(f"✗ Erro GraphQL: {data['errors']}")
                return False
            elif "data" in data:
                print("✓ Conexão com Pipefy OK")
                print(f"  Usuário: {data['data'].get('me', {}).get('name', 'N/A')}")
                return True
        else:
            print(f"✗ Erro HTTP: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"✗ Erro ao conectar: {str(e)}")
        return False
    
    print()

async def check_redis_connection():
    """Testa a conexão com Redis Upstash"""
    print("=" * 60)
    print("VERIFICANDO CONEXÃO COM REDIS")
    print("=" * 60)
    
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    
    if not redis_url or not redis_token:
        print("✗ Variáveis Redis não definidas")
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {redis_token}",
        }
        
        # Fazer um ping
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{redis_url}/ping",
                headers=headers,
                timeout=10.0
            )
        
        print(f"Status HTTP: {response.status_code}")
        
        if response.status_code in [200, 201]:
            print("✓ Conexão com Redis OK")
            return True
        else:
            print(f"✗ Erro Redis: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"✗ Erro ao conectar: {str(e)}")
        return False
    
    print()

async def check_courses_endpoints():
    """Testa os endpoints de cursos"""
    print("=" * 60)
    print("VERIFICANDO ENDPOINTS DE CURSOS")
    print("=" * 60)
    
    from api.scripts.courses import get_courses_unyleya, get_courses_pre_comite, get_courses_ymed
    
    endpoints = [
        ("Unyleya", get_courses_unyleya),
        ("Pré-Comitê", get_courses_pre_comite),
        ("YMED", get_courses_ymed),
    ]
    
    for name, endpoint_func in endpoints:
        try:
            print(f"\nTestando {name}...")
            courses = await endpoint_func()
            print(f"✓ {name}: {len(courses)} cursos encontrados")
        except Exception as e:
            print(f"✗ {name}: {str(e)[:200]}")

async def main():
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO DO BACKEND NPI")
    print("=" * 60 + "\n")
    
    check_env_vars()
    check_pipefy_connection()
    await check_redis_connection()
    
    # Descomentar para testar endpoints (requer que o backend esteja totalmente inicializado)
    # await check_courses_endpoints()
    
    print("\n" + "=" * 60)
    print("DIAGNÓSTICO CONCLUÍDO")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
