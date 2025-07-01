#!/usr/bin/env python3
"""
Script de execução em modo desenvolvimento para NPI-backend
Inicia a API com configurações otimizadas para desenvolvimento.
"""

import subprocess
import sys
import os
from pathlib import Path

# Configurações
PROJECT_ROOT = Path(__file__).parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / ("Scripts" if os.name == 'nt' else "bin") / ("python.exe" if os.name == 'nt' else "python")

def check_environment():
    """Verifica se o ambiente está configurado corretamente."""
    print("🔧 Verificando ambiente de desenvolvimento...")
    
    # Verifica se o ambiente virtual existe
    if not PYTHON_EXE.exists():
        print("❌ Ambiente virtual não encontrado!")
        print("   Execute: python setup.py")
        return False
    
    # Verifica se o arquivo .env existe
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print("⚠️  Arquivo .env não encontrado!")
        print("   Copiando .env.example para .env...")
        
        example_file = PROJECT_ROOT / ".env.example"
        if example_file.exists():
            with open(example_file, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("✅ Arquivo .env criado a partir do exemplo")
        else:
            print("❌ Arquivo .env.example não encontrado!")
            return False
    
    print("✅ Ambiente verificado com sucesso")
    return True

def start_development_server():
    """Inicia o servidor de desenvolvimento."""
    print("🚀 Iniciando NPI-backend em modo desenvolvimento...")
    print("📖 Documentação: http://localhost:8000/docs")
    print("🏥 Health Check: http://localhost:8000/monitoring/health")
    print("📊 Métricas: http://localhost:8000/monitoring/metrics")
    print("🔧 Admin: http://localhost:8000/admin/cache/stats")
    print("\n" + "="*60)
    print("🛑 Pressione Ctrl+C para parar o servidor")
    print("="*60 + "\n")
    
    try:
        # Configura variáveis de ambiente para desenvolvimento
        env = os.environ.copy()
        env['ENVIRONMENT'] = 'development'
        env['LOG_LEVEL'] = 'DEBUG'
        env['PYTHONPATH'] = str(PROJECT_ROOT)
        
        # Inicia uvicorn com configurações de desenvolvimento
        subprocess.run([
            str(PYTHON_EXE), "-m", "uvicorn", 
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",                    # Auto-reload em mudanças
            "--reload-dir", "api",         # Monitora apenas diretório api
            "--log-level", "info",         # Nível de log apropriado
            "--access-log",                # Log de acesso
            "--use-colors",                # Cores no terminal
            "--loop", "asyncio"            # Loop asyncio
        ], env=env, cwd=PROJECT_ROOT)
        
    except KeyboardInterrupt:
        print("\n🛑 Servidor parado pelo usuário")
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")
        return False
    
    return True

def main():
    """Função principal."""
    print("🚀 NPI-backend v2.0 - Modo Desenvolvimento")
    print("=" * 50)
    
    # Verifica ambiente
    if not check_environment():
        sys.exit(1)
    
    # Inicia servidor
    if not start_development_server():
        sys.exit(1)

if __name__ == "__main__":
    main()
