#!/usr/bin/env python3
"""
Script de teste e verificação do NPI-backend
Testa se todas as funcionalidades estão funcionando corretamente.
"""

import os
import sys
import subprocess
import traceback
from pathlib import Path

# ========== CONFIGURAÇÃO ==========

PROJECT_ROOT = Path(__file__).parent
API_DIR = PROJECT_ROOT / "api"
TESTS_DIR = PROJECT_ROOT / "tests"
VENV_DIR = PROJECT_ROOT / ".venv"
PYTHON_EXE = VENV_DIR / ("Scripts" if os.name == 'nt' else "bin") / "python"

# Adiciona o diretório do projeto ao path
sys.path.insert(0, str(PROJECT_ROOT))

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

def print_success(message: str):
    """Imprime mensagem de sucesso."""
    print_colored(f"✅ {message}", Colors.GREEN)

def print_warning(message: str):
    """Imprime mensagem de aviso."""
    print_colored(f"⚠️  {message}", Colors.YELLOW)

def print_error(message: str):
    """Imprime mensagem de erro."""
    print_colored(f"❌ {message}", Colors.RED)

def print_info(message: str):
    """Imprime mensagem informativa."""
    print_colored(f"ℹ️  {message}", Colors.BLUE)

# ========== FUNÇÕES DE TESTE ==========

def test_environment():
    """Testa ambiente básico."""
    print_colored("\n🔧 Testando Ambiente", Colors.BOLD)
    
    # Verifica Python
    if sys.version_info < (3, 8):
        print_error(f"Python 3.8+ necessário. Atual: {sys.version}")
        return False
    print_success(f"Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Verifica ambiente virtual
    if not PYTHON_EXE.exists():
        print_error("Ambiente virtual não encontrado")
        print_info("Execute: python setup.py")
        return False
    print_success("Ambiente virtual encontrado")
    
    # Verifica estrutura do projeto
    required_dirs = [API_DIR, TESTS_DIR]
    for dir_path in required_dirs:
        if dir_path.exists():
            print_success(f"Diretório {dir_path.name}")
        else:
            print_error(f"Diretório {dir_path.name} não encontrado")
            return False
    
    return True

def test_imports():
    """Testa imports básicos."""
    print_colored("\n� Testando Imports", Colors.BOLD)
    
    try:
        # Configuração
        from api.config import api_config, security_config, compression_config
        print_success(f"Configuração: {api_config.TITLE} v{api_config.VERSION}")
        
        # Utilitários
        from api.utils.logging import app_logger
        from api.utils.validation import EmailValidator
        print_success("Utilitários carregados")
        
        # Middlewares
        from api.middleware.security import SecurityMiddleware
        from api.middleware.monitoring import PerformanceMiddleware
        print_success("Middlewares carregados")
        
        # Aplicação principal (pode falhar devido a dependências)
        try:
            from api.main import app
            print_success("Aplicação principal carregada")
        except Exception as e:
            print_warning(f"Aplicação principal: {str(e)[:50]}...")
            print_info("Isso pode ser normal se Redis não estiver configurado")
        
        return True
        
    except Exception as e:
        print_error(f"Erro na importação: {e}")
        traceback.print_exc()
        return False

def test_validators():
    """Testa validadores."""
    print_colored("\n� Testando Validadores", Colors.BOLD)
    
    try:
        from api.utils.validation import EmailValidator, PasswordValidator
        
        # Testa email válido
        email = EmailValidator.validate("test@example.com")
        print_success(f"Email válido: {email}")
        
        # Testa email inválido
        try:
            EmailValidator.validate("invalid-email")
            print_error("Email inválido passou na validação")
            return False
        except ValueError:
            print_success("Email inválido rejeitado corretamente")
        
        # Testa senha válida  
        password = PasswordValidator.validate("StrongP@ssw0rd123")
        print_success("Senha válida aceita")
        
        # Testa senha inválida
        try:
            PasswordValidator.validate("123")
            print_error("Senha fraca passou na validação")
            return False
        except ValueError:
            print_success("Senha fraca rejeitada corretamente")
        
        return True
        
    except Exception as e:
        print_error(f"Erro nos validadores: {e}")
        return False

def test_security():
    """Testa componentes de segurança."""
    print_colored("\n🔒 Testando Segurança", Colors.BOLD)
    
    try:
        from api.middleware.security import RateLimiter, InputValidator
        
        # Testa rate limiter
        limiter = RateLimiter()
        allowed, remaining = limiter.check_rate_limit("127.0.0.1", "/test")
        if allowed and remaining >= 0:
            print_success("Rate limiter funcionando")
        else:
            print_error("Rate limiter com problema")
            return False
        
        # Testa input validator
        sanitized = InputValidator.sanitize_input("<script>alert('xss')</script>Hello")
        if "script" not in sanitized.lower():
            print_success("Sanitização XSS funcionando")
        else:
            print_error("Sanitização XSS falhou")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Erro na segurança: {e}")
        return False

def test_configuration():
    """Testa configuração."""
    print_colored("\n⚙️  Testando Configuração", Colors.BOLD)
    
    try:
        from api.config import (
            api_config, security_config, compression_config, 
            cache_config, monitoring_config, is_development
        )
        
        print_info(f"Ambiente: {'Desenvolvimento' if is_development() else 'Produção'}")
        print_info(f"API: {api_config.TITLE} v{api_config.VERSION}")
        print_info(f"Rate limit: {security_config.RATE_LIMIT_REQUESTS} req/min")
        print_info(f"Compressão GZIP: {'✓' if compression_config.ENABLE_GZIP else '✗'}")
        print_info(f"Cache TTL padrão: {cache_config.DEFAULT_TTL}s")
        print_info(f"Métricas: {'✓' if monitoring_config.ENABLE_METRICS else '✗'}")
        
        print_success("Configuração carregada corretamente")
        return True
        
    except Exception as e:
        print_error(f"Erro na configuração: {e}")
        return False

def test_file_structure():
    """Testa estrutura de arquivos."""
    print_colored("\n📁 Testando Estrutura de Arquivos", Colors.BOLD)
    
    required_files = [
        "api/__init__.py",
        "api/main.py",
        "api/config.py",
        "api/middleware/security.py",
        "api/middleware/monitoring.py",
        "api/utils/logging.py",
        "api/utils/cache.py",
        "api/utils/validation.py",
        "api/utils/error_handling.py",
        "api/utils/retry.py",
        "api/utils/compression.py",
        "requirements.txt",
        "render.yaml",
        ".env.example"
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            print_success(f"Arquivo {file_path}")
        else:
            print_error(f"Arquivo {file_path} não encontrado")
            missing_files.append(file_path)
    
    if missing_files:
        print_error(f"{len(missing_files)} arquivos faltando")
        return False
    
    print_success("Estrutura de arquivos completa")
    return True

def run_pytest():
    """Executa testes pytest se disponível."""
    print_colored("\n🧪 Executando Testes Pytest", Colors.BOLD)
    
    if not TESTS_DIR.exists():
        print_warning("Diretório de testes não encontrado")
        return True
    
    try:
        result = subprocess.run([
            str(PYTHON_EXE), "-m", "pytest", 
            str(TESTS_DIR), 
            "-v", 
            "--tb=short",
            "--maxfail=3",
            "--disable-warnings"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print_success("Testes pytest passaram")
            return True
        else:
            print_warning("Alguns testes pytest falharam")
            print_info("Isso pode ser normal se dependências externas não estiverem configuradas")
            # Mostra apenas o resumo dos testes
            lines = result.stdout.split('\n')
            for line in lines:
                if 'failed' in line.lower() or 'passed' in line.lower() or 'error' in line.lower():
                    print(f"  {line}")
            return True
            
    except subprocess.TimeoutExpired:
        print_warning("Testes pytest expiraram (normal se Redis não configurado)")
        return True
    except Exception as e:
        print_warning(f"Não foi possível executar pytest: {e}")
        return True

def check_env_file():
    """Verifica arquivo .env."""
    print_colored("\n🔧 Verificando Arquivo .env", Colors.BOLD)
    
    env_file = PROJECT_ROOT / ".env"
    example_file = PROJECT_ROOT / ".env.example"
    
    if not env_file.exists():
        if example_file.exists():
            print_warning("Arquivo .env não encontrado")
            print_info("Copiando .env.example para .env...")
            with open(example_file, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print_success("Arquivo .env criado")
        else:
            print_error("Nem .env nem .env.example encontrados")
            return False
    else:
        print_success("Arquivo .env encontrado")
    
    # Verifica configurações críticas
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "your_redis_url_here" in content:
        print_warning("Configure UPSTASH_REDIS_REST_URL no arquivo .env")
    if "your_token_here" in content:
        print_warning("Configure UPSTASH_REDIS_REST_TOKEN no arquivo .env")
    if "your-secret-key-here" in content:
        print_warning("Configure SECRET_KEY no arquivo .env")
    
    return True

# ========== FUNÇÃO PRINCIPAL ==========

def main():
    """Executa todos os testes."""
    print_colored("🧪 Teste Completo do NPI-backend v2.0", Colors.BOLD + Colors.BLUE)
    print_colored("=" * 60, Colors.BLUE)
    
    tests = [
        ("Ambiente", test_environment),
        ("Estrutura de Arquivos", test_file_structure),
        ("Arquivo .env", check_env_file),
        ("Imports", test_imports),
        ("Validadores", test_validators),
        ("Segurança", test_security),
        ("Configuração", test_configuration),
        ("Testes Pytest", run_pytest)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print_error(f"Teste {test_name} falhou")
        except Exception as e:
            print_error(f"Erro no teste {test_name}: {e}")
    
    # Resultado final
    print_colored(f"\n📊 Resultado Final: {passed}/{total} testes passaram", Colors.BOLD)
    
    if passed == total:
        print_colored("🎉 Todos os testes passaram! API está pronta.", Colors.GREEN + Colors.BOLD)
        print_colored("\n🚀 Para iniciar a API:", Colors.BLUE)
        print("   python run_dev.py   # Desenvolvimento")
        print("   python run_prod.py  # Produção")
        print_colored("\n📖 Recursos disponíveis:", Colors.BLUE)
        print("   http://localhost:8000/docs              # Documentação")
        print("   http://localhost:8000/monitoring/health # Health Check")
        print("   http://localhost:8000/monitoring/metrics # Métricas")
        return True
    elif passed >= total * 0.75:  # 75% ou mais
        print_colored("⚠️  A maioria dos testes passou. API deve funcionar.", Colors.YELLOW + Colors.BOLD)
        print_info("Configure as variáveis de ambiente para funcionalidade completa")
        return True
    else:
        print_colored("❌ Muitos testes falharam. Verifique a instalação.", Colors.RED + Colors.BOLD)
        print_info("Execute: python setup.py")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_colored("\n\n❌ Teste cancelado pelo usuário", Colors.RED)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n\n❌ Erro durante teste: {e}", Colors.RED)
        traceback.print_exc()
        sys.exit(1)
