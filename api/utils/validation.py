"""
Sistema de Validação Avançado para NPI-backend
Implementa validadores robustos para entrada de dados e modelos Pydantic.
"""

import re
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, date
from decimal import Decimal

from pydantic import BaseModel, validator, Field
from pydantic.validators import str_validator

from ..config import security_config
from ..utils.logging import validation_logger

# ========== VALIDADORES BASE ==========

class BaseValidator:
    """Classe base para validadores."""
    
    @staticmethod
    def not_empty(value: str, field_name: str = "field") -> str:
        """Valida que string não está vazia."""
        if not value or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        return value.strip()
    
    @staticmethod
    def min_length(value: str, min_len: int, field_name: str = "field") -> str:
        """Valida tamanho mínimo."""
        if len(value) < min_len:
            raise ValueError(f"{field_name} must be at least {min_len} characters long")
        return value
    
    @staticmethod
    def max_length(value: str, max_len: int, field_name: str = "field") -> str:
        """Valida tamanho máximo."""
        if len(value) > max_len:
            raise ValueError(f"{field_name} must be at most {max_len} characters long")
        return value
    
    @staticmethod
    def sanitize_html(value: str) -> str:
        """Remove ou sanitiza HTML perigoso."""
        dangerous_patterns = [
            r'<script.*?>.*?</script>',
            r'<iframe.*?>.*?</iframe>',
            r'javascript:',
            r'on\w+\s*=',
            r'<object.*?>.*?</object>',
            r'<embed.*?>.*?</embed>'
        ]
        
        for pattern in dangerous_patterns:
            value = re.sub(pattern, '', value, flags=re.IGNORECASE | re.DOTALL)
        
        return value

class EmailValidator(BaseValidator):
    """Validador específico para emails."""
    
    EMAIL_REGEX = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    @classmethod
    def validate(cls, value: str) -> str:
        """Valida formato de email."""
        value = cls.not_empty(value, "email")
        
        if not cls.EMAIL_REGEX.match(value):
            raise ValueError("Invalid email format")
        
        # Lista de domínios suspeitos (opcional)
        suspicious_domains = ['tempmail.com', '10minutemail.com']
        domain = value.split('@')[1].lower()
        
        if domain in suspicious_domains:
            validation_logger.warning("Suspicious email domain detected", email=value, domain=domain)
        
        return value.lower()

class PasswordValidator(BaseValidator):
    """Validador específico para senhas."""
    
    @classmethod
    def validate(cls, value: str) -> str:
        """Valida força da senha."""
        value = cls.not_empty(value, "password")
        
        # Tamanho mínimo e máximo
        cls.min_length(value, security_config.MIN_PASSWORD_LENGTH, "password")
        cls.max_length(value, security_config.MAX_PASSWORD_LENGTH, "password")
        
        # Caracteres especiais se requerido
        if security_config.REQUIRE_SPECIAL_CHARS:
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
                raise ValueError("Password must contain at least one special character")
        
        # Verifica se não é muito simples
        simple_patterns = [
            r'^(123456|password|qwerty|abc123)$',
            r'^(.)\1{7,}$',  # Mesmo caractere repetido
            r'^(012345|987654)$'
        ]
        
        for pattern in simple_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                raise ValueError("Password is too simple")
        
        return value

class PhoneValidator(BaseValidator):
    """Validador específico para telefones."""
    
    PHONE_REGEX = re.compile(r'^\+?[\d\s\-\(\)]{10,15}$')
    
    @classmethod
    def validate(cls, value: str) -> str:
        """Valida formato de telefone."""
        if not value:
            return value
        
        # Remove espaços e caracteres especiais para validação
        clean_phone = re.sub(r'[\s\-\(\)]', '', value)
        
        if not cls.PHONE_REGEX.match(value):
            raise ValueError("Invalid phone format")
        
        # Valida se tem número suficiente de dígitos
        digits_only = re.sub(r'\D', '', clean_phone)
        if len(digits_only) < 10 or len(digits_only) > 15:
            raise ValueError("Phone must have between 10 and 15 digits")
        
        return value

class CPFValidator(BaseValidator):
    """Validador específico para CPF brasileiro."""
    
    @classmethod
    def validate(cls, value: str) -> str:
        """Valida CPF brasileiro."""
        if not value:
            return value
        
        # Remove caracteres não numéricos
        cpf = re.sub(r'\D', '', value)
        
        # Verifica se tem 11 dígitos
        if len(cpf) != 11:
            raise ValueError("CPF must have 11 digits")
        
        # Verifica se não são todos iguais
        if cpf == cpf[0] * 11:
            raise ValueError("Invalid CPF format")
        
        # Validação do algoritmo do CPF
        if not cls._validate_cpf_algorithm(cpf):
            raise ValueError("Invalid CPF")
        
        # Formata CPF
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    
    @staticmethod
    def _validate_cpf_algorithm(cpf: str) -> bool:
        """Valida algoritmo do CPF."""
        def calculate_digit(cpf_digits, weights):
            total = sum(int(digit) * weight for digit, weight in zip(cpf_digits, weights))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder
        
        # Primeiro dígito verificador
        first_digit = calculate_digit(cpf[:9], range(10, 1, -1))
        if first_digit != int(cpf[9]):
            return False
        
        # Segundo dígito verificador
        second_digit = calculate_digit(cpf[:10], range(11, 1, -1))
        return second_digit == int(cpf[10])

class URLValidator(BaseValidator):
    """Validador específico para URLs."""
    
    URL_REGEX = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    @classmethod
    def validate(cls, value: str) -> str:
        """Valida formato de URL."""
        if not value:
            return value
        
        value = value.strip()
        
        if not cls.URL_REGEX.match(value):
            raise ValueError("Invalid URL format")
        
        # Verifica protocolo seguro em produção
        from ..config import is_production
        if is_production() and not value.startswith('https://'):
            validation_logger.warning("Non-HTTPS URL detected in production", url=value)
        
        return value

# ========== VALIDADORES CUSTOMIZADOS PYDANTIC ==========

def validate_email_field(value: str) -> str:
    """Validador Pydantic para email."""
    return EmailValidator.validate(value)

def validate_password_field(value: str) -> str:
    """Validador Pydantic para senha."""
    return PasswordValidator.validate(value)

def validate_phone_field(value: str) -> str:
    """Validador Pydantic para telefone."""
    return PhoneValidator.validate(value)

def validate_cpf_field(value: str) -> str:
    """Validador Pydantic para CPF."""
    return CPFValidator.validate(value)

def validate_url_field(value: str) -> str:
    """Validador Pydantic para URL."""
    return URLValidator.validate(value)

def validate_course_name(value: str) -> str:
    """Validador específico para nome de curso."""
    value = BaseValidator.not_empty(value, "course name")
    value = BaseValidator.min_length(value, 5, "course name")
    value = BaseValidator.max_length(value, 200, "course name")
    value = BaseValidator.sanitize_html(value)
    
    # Verifica se não contém apenas números
    if value.isdigit():
        raise ValueError("Course name cannot be only numbers")
    
    return value

def validate_workload(value: int) -> int:
    """Validador para carga horária."""
    if value <= 0:
        raise ValueError("Workload must be positive")
    
    if value > 10000:  # Limite razoável
        raise ValueError("Workload seems too high")
    
    return value

def validate_status(value: str) -> str:
    """Validador para status de curso."""
    valid_statuses = [
        "pendente", "aprovado", "rejeitado", "em_analise", 
        "aguardando", "suspenso", "cancelado"
    ]
    
    value = value.lower().strip()
    
    if value not in valid_statuses:
        raise ValueError(f"Status must be one of: {', '.join(valid_statuses)}")
    
    return value

# ========== MODELOS BASE MELHORADOS ==========

class ValidatedBaseModel(BaseModel):
    """Modelo base com validações avançadas."""
    
    class Config:
        # Configurações gerais
        validate_assignment = True
        allow_reuse = True
        extra = "forbid"  # Não permite campos extras
        str_strip_whitespace = True  # Remove espaços automaticamente
        
        # Serialização
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }
    
    @validator('*', pre=True)
    def prevent_xss(cls, value):
        """Previne XSS em todos os campos string."""
        if isinstance(value, str):
            return BaseValidator.sanitize_html(value)
        return value

class PaginationModel(ValidatedBaseModel):
    """Modelo para paginação."""
    
    page: int = Field(default=1, ge=1, description="Page number")
    size: int = Field(default=20, ge=1, le=100, description="Page size")
    
    @validator('size')
    def validate_page_size(cls, value):
        """Valida tamanho da página."""
        if value > 100:
            raise ValueError("Page size cannot exceed 100")
        return value

class SearchModel(ValidatedBaseModel):
    """Modelo para busca."""
    
    query: str = Field(min_length=1, max_length=200, description="Search query")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Search filters")
    
    @validator('query')
    def validate_search_query(cls, value):
        """Valida query de busca."""
        # Remove caracteres perigosos
        dangerous_chars = ['<', '>', '"', "'", ';', '(', ')', '{', '}']
        for char in dangerous_chars:
            if char in value:
                raise ValueError(f"Invalid character '{char}' in search query")
        
        return value

# ========== DECORADORES DE VALIDAÇÃO ==========

def validate_input(validator_func: Callable):
    """Decorator para validação de entrada em endpoints."""
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                # Aplica validação
                for arg in args:
                    if hasattr(arg, '__dict__'):  # Se é um objeto
                        for key, value in arg.__dict__.items():
                            if isinstance(value, str):
                                validator_func(value)
                
                return await func(*args, **kwargs)
                
            except ValueError as e:
                validation_logger.warning(
                    "Input validation failed",
                    function=func.__name__,
                    error=str(e)
                )
                raise
        
        return wrapper
    return decorator

def log_validation_error(func):
    """Decorator para logging de erros de validação."""
    
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            validation_logger.error(
                "Validation error occurred",
                function=func.__name__,
                error=str(e),
                args=str(args)[:200]  # Limita tamanho do log
            )
            raise
    
    return wrapper

# ========== UTILITÁRIOS ==========

def create_validator_chain(*validators: Callable) -> Callable:
    """Cria cadeia de validadores."""
    
    def validate(value):
        for validator in validators:
            value = validator(value)
        return value
    
    return validate

def batch_validate(data: Dict[str, Any], validators: Dict[str, Callable]) -> Dict[str, Any]:
    """Valida múltiplos campos de uma vez."""
    
    validated_data = {}
    errors = {}
    
    for field, value in data.items():
        if field in validators:
            try:
                validated_data[field] = validators[field](value)
            except ValueError as e:
                errors[field] = str(e)
        else:
            validated_data[field] = value
    
    if errors:
        validation_logger.error("Batch validation failed", errors=errors)
        raise ValueError(f"Validation errors: {errors}")
    
    return validated_data
