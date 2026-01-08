# Diagnóstico e Correção do Erro HTTP 500

## Problema Relatado
O frontend estava recebendo erro HTTP 500 (Internal Server Error) ao tentar acessar:
- `/courses` - Buscando cursos Unyleya
- `/pre-comite-courses` - Buscando cursos pré-comitê  
- `/course-proposal` - Endpoint não encontrado no backend

## Análise Realizada

### Causas Identificadas
1. **Falta de Logging Detalhado**: Os erros eram capturados mas não exibiam informações suficientes
2. **Tratamento Genérico de Exceções**: Todas as exceções resultavam em "Falha ao buscar cursos"
3. **Falta de Diagnóstico**: Sem endpoint para verificar conectividade com Pipefy

### Potenciais Causas do Erro 500
1. **Conexão com Pipefy**: Token expirado, inválido ou revogado
2. **Parsing de Dados**: Erro ao processar resposta JSON da API Pipefy
3. **Conexão com Redis**: Falha ao armazenar em cache
4. **Timeout**: Timeout na requisição para Pipefy ou Redis

## Correções Implementadas

### 1. Melhorado Logging em `api/scripts/courses.py`
- Adicionado `import logging` e `traceback`
- Funções agora exibem stack trace completo ao falhar:
  - `get_courses_pre_comite()`
  - `get_courses_unyleya()`
  - `get_courses_ymed()`

### 2. Adicionado Try-Catch nos Endpoints (`api/main.py`)
- `/courses` - Logging detalhado com mensagens descritivas
- `/pre-comite-courses` - Logging detalhado com mensagens descritivas
- `/courses-ymed` - Logging detalhado com mensagens descritivas

### 3. Novo Endpoint de Diagnóstico
- `GET /diagnostic/pipefy` - Testa conectividade com API Pipefy
- Retorna status da conexão e primeiras 500 caracteres da resposta
- Requer autenticação básica

### 4. Logging Melhorado no Parsing
- Adicionado logging ao iniciar parsing
- Warnings para edges sem dados
- Logging de erros específicos ao processar campos

## Como Testar

### 1. Verificar Diagnóstico de Pipefy
```bash
curl -X GET "http://localhost:8000/diagnostic/pipefy" \
  -u username:password
```

### 2. Ativar Logging Detalhado
O servidor agora exibe logs mais detalhados. Verifique os logs no terminal/console.

### 3. Executar Script de Diagnóstico
```bash
python diagnostic.py
```

Este script verifica:
- ✓ Variáveis de ambiente obrigatórias
- ✓ Conexão com Pipefy API
- ✓ Conexão com Redis Upstash

## Recomendações para Próximas Etapas

### Imediato
1. **Verifique a PIPEFY_API_KEY**: Pode estar expirada
2. **Execute o diagnóstico**: `python diagnostic.py`
3. **Teste o endpoint**: `GET /diagnostic/pipefy`
4. **Verifique os logs**: Procure por mensagens de erro detalhadas

### Médio Prazo
1. **Implementar retry logic**: Adicionar tentativas automáticas em caso de timeout
2. **Rate limiting**: Implementar rate limit para evitar throttling do Pipefy
3. **Cache invalidation**: Adicionar estratégia de invalidação de cache

### Longo Prazo
1. **Monitoramento**: Implementar alertas para falhas de API
2. **Circuit breaker**: Implementar padrão circuit breaker para falhas cascata
3. **Fallback data**: Manter dados em cache para fallback em caso de falha

## Commits Realizados

```
feat: melhorar tratamento de erros e logging nos endpoints de cursos
- Adicionar logging detalhado em courses.py com traceback
- Adicionar try-catch com mensagens descritivas nos endpoints
- Criar endpoint de diagnóstico /diagnostic/pipefy
- Melhorar mensagens de erro para facilitar debugging
```

## Arquivos Modificados

- `api/main.py`:
  - Endpoints `/courses`, `/pre-comite-courses`, `/courses-ymed`
  - Novo endpoint `GET /diagnostic/pipefy`

- `api/scripts/courses.py`:
  - Melhorado logging em `get_courses_pre_comite()`
  - Melhorado logging em `get_courses_unyleya()`
  - Melhorado logging em `get_courses_ymed()`
  - Melhorado logging no parsing de dados
  - Adicionado traceback nos catches

- `diagnostic.py` (novo arquivo):
  - Script para diagnóstico de conectividade

## Próximos Passos

1. **Deploy** das mudanças no Render.com
2. **Execute** o diagnóstico após deploy
3. **Monitore** os logs por erros detalhados
4. **Ajuste** conforme necessário baseado no diagnostic output
