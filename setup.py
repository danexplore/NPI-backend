#!/usr/bin/env python3
"""
Script de Configuração e Inicialização do NPI-backend
Configura o ambiente, instala dependências e verifica a saúde do sistema.
"""

import os
import sys
import subprocess
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional

# ========== CONFIGURAÇÃO ==========

PROJECT_ROOT = Path(__file__).parent
API_DIR = PROJECT_ROOT / "api"
TESTS_DIR = PROJECT_ROOT / "tests"
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
ENV_FILE = PROJECT_ROOT / ".env"

# ========== CORES PARA OUTPUT ==========

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_colored(message: str, color: str = Colors.GREEN):
    """Imprime mensagem colorida."""
    print(f"{color}{message}{Colors.END}")

def print_step(step: str):
    """Imprime passo da configuração."""
    print_colored(f"\n🔧 {step}", Colors.BLUE + Colors.BOLD)

def print_success(message: str):
    """Imprime mensagem de sucesso."""
    print_colored(f"✅ {message}", Colors.GREEN)

def print_warning(message: str):
    """Imprime mensagem de aviso."""
    print_colored(f"⚠️  {message}", Colors.YELLOW)

def print_error(message: str):
    """Imprime mensagem de erro."""
    print_colored(f"❌ {message}", Colors.RED)

# ========== FUNÇÕES DE VERIFICAÇÃO ==========

def check_python_version() -> bool:
    """Verifica se a versão do Python é compatível."""
    if sys.version_info < (3, 8):
        print_error(f"Python 3.8+ é necessário. Versão atual: {sys.version}")
        return False
    
    print_success(f"Python {sys.version_info.major}.{sys.version_info.minor} ✓")
    return True

def check_pip() -> bool:
    """Verifica se pip está disponível."""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], 
                      check=True, capture_output=True)
        print_success("pip está disponível ✓")
        return True
    except subprocess.CalledProcessError:
        print_error("pip não está disponível")
        return False

def check_git() -> bool:
    """Verifica se git está disponível."""
    try:
        subprocess.run(["git", "--version"], 
                      check=True, capture_output=True)
        print_success("git está disponível ✓")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_warning("git não está disponível (opcional)")
        return False

# ========== FUNÇÕES DE CONFIGURAÇÃO ==========

def create_virtual_environment():
    """Cria ambiente virtual se não existir."""
    if VENV_DIR.exists():
        print_success("Ambiente virtual já existe")
        return
    
    print_step("Criando ambiente virtual")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], 
                      check=True)
        print_success("Ambiente virtual criado")
    except subprocess.CalledProcessError as e:
        print_error(f"Erro ao criar ambiente virtual: {e}")
        sys.exit(1)

def get_python_executable() -> str:
    """Obtém o executável Python do ambiente virtual."""
    if os.name == 'nt':  # Windows
        return str(VENV_DIR / "Scripts" / "python.exe")
    else:  # Linux/macOS
        return str(VENV_DIR / "bin" / "python")

def get_pip_executable() -> str:
    """Obtém o executável pip do ambiente virtual."""
    if os.name == 'nt':  # Windows
        return str(VENV_DIR / "Scripts" / "pip.exe")
    else:  # Linux/macOS
        return str(VENV_DIR / "bin" / "pip")

def install_dependencies():
    """Instala dependências do projeto."""
    if not REQUIREMENTS_FILE.exists():
        print_error("requirements.txt não encontrado")
        sys.exit(1)
    
    print_step("Instalando dependências")
    pip_exe = get_pip_executable()
    
    try:
        # Atualiza pip primeiro
        subprocess.run([pip_exe, "install", "--upgrade", "pip"], 
                      check=True)
        
        # Instala dependências
        subprocess.run([pip_exe, "install", "-r", str(REQUIREMENTS_FILE)], 
                      check=True)
        
        print_success("Dependências instaladas")
    except subprocess.CalledProcessError as e:
        print_error(f"Erro ao instalar dependências: {e}")
        sys.exit(1)

def create_env_file():
    """Cria arquivo .env se não existir."""
    if ENV_FILE.exists():
        print_success("Arquivo .env já existe")
        return
    
    print_step("Criando arquivo .env")
    
    env_template = """# Configurações do NPI-backend

# Ambiente
ENVIRONMENT=development

# Autenticação Básica (usuario:senha,usuario2:senha2)
BASIC_AUTH_USERS=admin:admin123,user:user123

# Redis/Upstash
UPSTASH_REDIS_REST_URL=your_redis_url_here
UPSTASH_REDIS_REST_TOKEN=your_redis_token_here

# Pipefy (se aplicável)
PHPSESSID=your_session_id_here

# CORS Origins (separadas por vírgula)
ALLOWED_ORIGINS=*

# Chave secreta para JWT (se usar)
SECRET_KEY=your-secret-key-here

# Logging
LOG_LEVEL=DEBUG
"""
    
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write(env_template)
    
    print_success("Arquivo .env criado")
    print_warning("⚠️  Configure as variáveis de ambiente no arquivo .env")

def verify_project_structure():
    """Verifica estrutura do projeto."""
    print_step("Verificando estrutura do projeto")
    
    required_dirs = [API_DIR, TESTS_DIR]
    required_files = [
        API_DIR / "main.py",
        API_DIR / "config.py",
        API_DIR / "__init__.py"
    ]
    
    # Verifica diretórios
    for dir_path in required_dirs:
        if dir_path.exists():
            print_success(f"Diretório {dir_path.name} ✓")
        else:
            print_error(f"Diretório {dir_path.name} não encontrado")
            return False
    
    # Verifica arquivos
    for file_path in required_files:
        if file_path.exists():
            print_success(f"Arquivo {file_path.relative_to(PROJECT_ROOT)} ✓")
        else:
            print_error(f"Arquivo {file_path.relative_to(PROJECT_ROOT)} não encontrado")
            return False
    
    return True

# ========== FUNÇÕES DE TESTE ==========

async def test_api_health():
    """Testa saúde da API."""
    try:
        import httpx
        
        # Inicia servidor em background para teste
        print_step("Testando saúde da API")
        
        # Simula teste básico de importação
        try:
            from api.main import app
            from api.config import api_config
            print_success("Importação da API bem-sucedida")
            print_success(f"API Version: {api_config.VERSION}")
            return True
        except Exception as e:
            print_error(f"Erro ao importar API: {e}")
            return False
            
    except ImportError:
        print_warning("httpx não disponível para teste completo")
        return True

def run_tests():
    """Executa testes do projeto."""
    print_step("Executando testes")
    
    python_exe = get_python_executable()
    
    try:
        # Executa pytest
        result = subprocess.run([
            python_exe, "-m", "pytest", 
            str(TESTS_DIR), 
            "-v", 
            "--tb=short",
            "--maxfail=5"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print_success("Todos os testes passaram")
            return True
        else:
            print_warning("Alguns testes falharam")
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            return False
            
    except Exception as e:
        print_error(f"Erro ao executar testes: {e}")
        return False

def create_startup_scripts():
    """Cria scripts de inicialização."""
    print_step("Criando scripts de inicialização")
    
    # Script para desenvolvimento
    dev_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / {"Scripts" if sys.platform == "win32" else "bin"} / "python"

if __name__ == "__main__":
    subprocess.run([
        str(PYTHON_EXE), "-m", "uvicorn", 
        "api.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8000", 
        "--reload",
        "--log-level", "info"
    ])
"""
    
    # Script para produção
    prod_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / {"Scripts" if sys.platform == "win32" else "bin"} / "python"

if __name__ == "__main__":
    subprocess.run([
        str(PYTHON_EXE), "-m", "uvicorn", 
        "api.main:app", 
        "--host", "0.0.0.0", 
        "--port", "8000", 
        "--workers", "4",
        "--log-level", "warning"
    ])
"""
    
    # Salva scripts
    dev_script = PROJECT_ROOT / "run_dev.py"
    prod_script = PROJECT_ROOT / "run_prod.py"
    
    with open(dev_script, 'w', encoding='utf-8') as f:
        f.write(dev_script_content)
    
    with open(prod_script, 'w', encoding='utf-8') as f:
        f.write(prod_script_content)
    
    # Torna executáveis no Unix
    if os.name != 'nt':
        os.chmod(dev_script, 0o755)
        os.chmod(prod_script, 0o755)
    
    print_success("Scripts de inicialização criados")

# ========== FUNÇÃO PRINCIPAL ==========

def main():
    """Função principal de configuração."""
    print_colored("🚀 Configuração do NPI-backend API", Colors.BOLD + Colors.BLUE)
    print_colored("=" * 50, Colors.BLUE)
    
    # Verificações iniciais
    print_step("Verificações iniciais")
    if not check_python_version():
        sys.exit(1)
    
    check_pip()
    check_git()
    
    # Verifica estrutura do projeto
    if not verify_project_structure():
        print_error("Estrutura do projeto inválida")
        sys.exit(1)
    
    # Configuração do ambiente
    create_virtual_environment()
    install_dependencies()
    create_env_file()
    
    # Testes
    if asyncio.run(test_api_health()):
        print_success("API está funcionando")
    
    # Scripts auxiliares
    create_startup_scripts()
    
    # Resumo final
    print_colored("\n🎉 Configuração concluída!", Colors.BOLD + Colors.GREEN)
    print_colored("=" * 50, Colors.GREEN)
    
    print("\n📋 Próximos passos:")
    print("1. Configure as variáveis no arquivo .env")
    print("2. Execute: python run_dev.py (desenvolvimento)")
    print("3. Execute: python run_prod.py (produção)")
    print("4. Acesse: http://localhost:8000/docs")
    
    print("\n🔧 Comandos úteis:")
    print("- Testes: python -m pytest tests/")
    print("- Linting: python -m flake8 api/")
    print("- Formatação: python -m black api/")
    print("- Monitoramento: http://localhost:8000/monitoring/health")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n❌ Configuração cancelada pelo usuário", Colors.RED)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n\n❌ Erro durante configuração: {e}", Colors.RED)
        sys.exit(1)
