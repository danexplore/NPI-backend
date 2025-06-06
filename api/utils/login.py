from fastapi import HTTPException
import jwt
from datetime import datetime, timedelta, UTC
from ..models import LoginRequest, TokenRequest, User
from typing import Dict
import os
import bcrypt
import httpx

API_URL = "https://api.pipefy.com/graphql"
PIPEFY_API_KEY = os.getenv("PIPEFY_API_KEY")

if not PIPEFY_API_KEY:
    raise ValueError("PIPEFY_API_KEY não está definida nas variáveis de ambiente")

HEADERS = {
    "Authorization": f"Bearer {PIPEFY_API_KEY}",
    "Content-Type": "application/json",
}

async def fetch_users_from_pipefy():
    all_users: Dict[int, User] = {}

    query = """
    {
        table_records(table_id: 306263425, first: 50) {
            nodes {
                id
                record_fields {
                    name
                    native_value
                    field {
                        id
                    }
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
    
    user = User(
        id=0,
        nome="",
        email="",
        password="",
        permissao=""
    )

    try:
        cursor = None
        has_next_page = True

        async with httpx.AsyncClient() as client:
            while has_next_page:
                paginated_query = query
                if cursor:
                    paginated_query = query.replace(
                        'first: 50', f'first: 50, after: "{cursor}"'
                    )

                response = await client.post(
                    API_URL,
                    headers=HEADERS,
                    json={"query": paginated_query}
                )

                if not response.is_success:
                    print(f"Erro na requisição ao Pipefy: {response.text}")
                    return {}

                data = response.json().get("data", {}).get("table_records", {})
                nodes = data.get("nodes", [])
                page_info = data.get("pageInfo", {})

                for node in nodes:
                    user.id = node.get("id")
                    for field in node.get("record_fields", []):
                        field_id = field.get("field", {}).get("id")
                        value = field.get("native_value")
                        if field_id == "email":
                            user.email = value
                        elif field_id == "nome_completo":
                            user.nome = value
                        elif field_id == "senha":
                            user.password = value
                        elif field_id == "permiss_o":
                            user.permissao = value

                    all_users[user.id] = user

                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")

    except Exception as e:
        print(f"Erro ao buscar usuários do Pipefy: {e}")
        return {}
    
    return all_users

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

async def login(request: LoginRequest):
    users = await fetch_users_from_pipefy()
    if not users:
        raise HTTPException(status_code=500, detail="Erro ao buscar usuários")

    if not request.email or not request.password:
        raise HTTPException(status_code=400, detail="Email e senha são obrigatórios")
    
    def get_user_by_email(email: str) -> User:
        for user in users.values():
            if user.email == email:
                return user
        return None
    user = get_user_by_email(request.email)
    
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not verify_password(request.password, user.password):
        raise HTTPException(status_code=401, detail="Senha incorreta")
    
    payload = {
        "email": request.email,
        "name": user.nome,
        "role": user.permissao,
        "exp": datetime.now(UTC) + timedelta(days=7)
    }

    token = jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user.id,
            "email": request.email,
            "name": user.nome,
            "role": user.permissao
        }
    }

async def verify_token(request: TokenRequest):
    if not request.token:
        raise HTTPException(status_code=400, detail="Token não fornecido")
    
    try:
        payload = jwt.decode(request.token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        return {
            "valid": True,
            "user": {
                "email": payload['email'],
                "name": payload['name'],
                "role": payload['role']
            }
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

async def create_password_hash(password: str, card_id: int):
    plain_password = password
    
    if not password:
        raise HTTPException(status_code=400, detail="Senha não pode ser vazia")
    if not card_id:
        raise HTTPException(status_code=400, detail="ID do cartão não pode ser vazio")
    
    # Criptografar a senha
    hashed_password = hash_password(plain_password)
    
    query = """
    mutation {
        updateCardField(input: {card_id: %d, field_id: "senha", new_value: "%s"}) {
            card {
                id
            }
        }
    }
    """ % (card_id, hashed_password)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            headers=HEADERS,
            json={"query": query}
        )
        if response.status_code == 200:
            return {
                "success": True,
                "message": "Senha gerada com sucesso. Verifique seu email.",
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail="Erro ao gerar senha: " + response.text
            )
        
async def reset_password(card_id: int, new_password: str):
    if not card_id:
        raise HTTPException(status_code=400, detail="ID do cartão não pode ser vazio")
    if not new_password:
        raise HTTPException(status_code=400, detail="Nova senha não pode ser vazia")
    
    hashed_password = hash_password(new_password)
    
    query = """
    mutation {
        updateCardField(input: {card_id: %d, field_id: "senha", new_value: "%s"}) {
            card {
                id
            }
        }
    }
    """ % (card_id, hashed_password)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            headers=HEADERS,
            json={"query": query}
        )
        if response.status_code == 200:
            return {
                "success": True,
                "message": "Senha redefinida com sucesso."
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail="Erro ao redefinir senha: " + response.text
            )