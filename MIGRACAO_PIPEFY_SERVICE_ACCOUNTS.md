# Guia de Migração: Pipefy API - De Bearer Token para Service Accounts

## Status
✅ Infra de autenticação criada
⚠️ Arquivos criados, aguardando verificação das credenciais

## O que mudou

### Antes (Deprecated)
```python
PIPEFY_API_KEY = os.getenv("PIPEFY_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {PIPEFY_API_KEY}",
    "Content-Type": "application/json",
}
```

### Agora (Service Accounts - OAuth 2.0)
```python
# Nova autenticação via Service Account
headers = await get_pipefy_headers()
```

## Arquivos Criados/Modificados

### 🆕 api/lib/pipefy_auth.py (NOVO)
- Módulo centralizado de autenticação
- Gerencia tokens OAuth 2.0
- Cache automático de tokens com expiração
- Suporta modo fallback para token legado

**Funcionalidades:**
- `get_pipefy_token()` - Obtém token OAuth 2.0 com retry
- `get_pipefy_headers()` - Retorna headers prontos para requisições
- `get_pipefy_headers_sync()` - Versão síncrona (apenas legacy)
- Cache com TTL automático (5 minutos antes da expiração)

### ✏️ api/scripts/courses_new.py (NOVO)
- Versão refatorada com nova autenticação
- Todas as requisições usam `await get_pipefy_headers()`
- Mantém lógica de parsing e tratamento de erros

### ✏️ api/scripts/login.py (MODIFICADO)
- Atualizado para usar novo módulo de autenticação
- Ainda precisa de ajustes nas requisições

## Variáveis de Ambiente Necessárias

### Opção 1: Service Accounts (RECOMENDADO)
```bash
PIPEFY_SERVICE_ACCOUNT_ID=seu_id_da_conta_de_servico
PIPEFY_SERVICE_ACCOUNT_SECRET=seu_secret_da_conta_de_servico
```

### Opção 2: Token Legado (DEPRECATED - Fallback)
```bash
PIPEFY_API_KEY=seu_token_legado
```

## Como Migrar

### Passo 1: Obter Credenciais de Service Account no Pipefy
1. Acesse https://app.pipefy.com
2. Vá em Configurações > Integrações > Service Accounts
3. Crie uma nova Service Account
4. Copie o `ID` e `Secret`

### Passo 2: Configurar Variáveis de Ambiente

**No arquivo .env local:**
```env
PIPEFY_SERVICE_ACCOUNT_ID=xxxxxxxxxxxxx
PIPEFY_SERVICE_ACCOUNT_SECRET=xxxxxxxxxxxxx
```

**No Render.com (Production):**
1. Dashboard > Environment > Environment Variables
2. Adicione:
   - `PIPEFY_SERVICE_ACCOUNT_ID`
   - `PIPEFY_SERVICE_ACCOUNT_SECRET`
3. Remova `PIPEFY_API_KEY` se não precisar mais (fallback)

### Passo 3: Substituir Arquivo courses.py
```bash
# Backup do arquivo atual
mv api/scripts/courses.py api/scripts/courses_old.py

# Usar novo arquivo
mv api/scripts/courses_new.py api/scripts/courses.py
```

### Passo 4: Atualizar Todas as Requisições em login.py
Substituir todas as linhas:
```python
headers=HEADERS,
```

Por:
```python
headers=await get_pipefy_headers(),
```

Deixar a função `async`.

### Passo 5: Testar
```bash
python diagnostic.py
```

## Benefícios da Migração

✅ **Segurança**: Tokens com expiração automática (1 hora)
✅ **Performance**: Cache de tokens reduz requisições
✅ **Confiabilidade**: Gerenciamento automático de expiração
✅ **Compatibilidade**: Fallback para token legado se necessário
✅ **Logging**: Rastreamento detalhado de autenticação

## Troubleshooting

### Erro: "Service Account não configurado"
- Verifique se `PIPEFY_SERVICE_ACCOUNT_ID` e `PIPEFY_SERVICE_ACCOUNT_SECRET` estão definidos
- Ou configure `PIPEFY_API_KEY` como fallback

### Erro: "Token expirado"
- O módulo renova automaticamente
- Se persistir, verifique credenciais de Service Account no Pipefy

### Erro: "Erro ao obter token Pipefy"
- Confirme que as credenciais de Service Account são válidas
- Teste manualmente usando `curl`:
```bash
curl -X POST https://api.pipefy.com/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=seu_id" \
  -d "client_secret=seu_secret"
```

## Próximos Passos

1. ✅ Criar módulo de autenticação centralizado
2. ⏳ Obter credenciais de Service Account do Pipefy
3. ⏳ Configurar variáveis de ambiente
4. ⏳ Substituir `courses.py` pelo `courses_new.py`
5. ⏳ Atualizar requisições em `login.py`
6. ⏳ Testar localmente
7. ⏳ Deploy em staging
8. ⏳ Deploy em production

## Referências

- [Pipefy Service Accounts Documentation](https://docs.pipefy.com)
- [OAuth 2.0 Client Credentials](https://tools.ietf.org/html/rfc6749#section-4.4)
