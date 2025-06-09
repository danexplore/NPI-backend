from fastapi import HTTPException
import jwt
from datetime import datetime, timedelta, UTC
from ..models import User
from typing import Dict
import os
import bcrypt
import httpx
from dotenv import load_dotenv

if os.getenv("ENVIRONMENT") == "development":
    load_dotenv()

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
                    value
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
        permissao="",
        card_id=0
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
                        value = field.get("value")
                        if field_id == "email":
                            user.email = value
                        elif field_id == "nome_completo":
                            user.nome = value
                        elif field_id == "senha":
                            user.password = value
                        elif field_id == "permiss_o":
                            user.permissao = value
                        elif field_id == "card_id":
                            user.card_id = int(value)

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
    is_same = bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    return {"is_same": is_same}

async def login(email: str, password: str):
    try:
        users = await fetch_users_from_pipefy()
        if not users:
            raise HTTPException(status_code=500, detail="Erro ao buscar usuários")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email e senha são obrigatórios")
        
        def get_user_by_email(email: str) -> User:
            for user in users.values():
                if user.email == email:
                    return user
            return None
        user = get_user_by_email(email)
        
        if not user:
            raise HTTPException(status_code=401, detail="Usuário não encontrado")
        if not verify_password(password, user.password).get("is_same", False):
            raise HTTPException(status_code=401, detail="Senha incorreta")
        
        payload = {
            "id": user.id,
            "email": email,
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
                "email": email,
                "name": user.nome,
                "role": user.permissao
            }
        }
    except Exception as e:
        return {"error": f"Erro ao realizar o login.", "message": e.detail}

async def verify_token(token: str):
    if not token:
        raise HTTPException(status_code=400, detail="Token não fornecido")
    
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        return {
            "id": payload['id'],
            "email": payload['email'],
            "name": payload['name'],
            "role": payload['role']
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
            if "errors" in response.json():
                raise HTTPException(
                    status_code=400,
                    detail="Erro ao atualizar senha: " + str(response.json()["errors"][0]["message"])
                )
            return {
                "success": True,
                "message": "Senha gerada com sucesso. Verifique seu email."
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail="Erro ao gerar senha: " + response.text
            )   
        
async def reset_password(user_id: str, new_password: str):
    if not user_id:
        raise HTTPException(status_code=400, detail="ID do usuário não pode ser vazio")
    if not new_password:
        raise HTTPException(status_code=400, detail="Nova senha não pode ser vazia")
    
    hashed_password = hash_password(new_password)
    
    query = f"""
    mutation {{
        setTableRecordFieldValue(
            input: {{table_record_id: "{user_id}", field_id: "senha", value: "{hashed_password}"}}
        ) {{
            table_record {{
                id
            }}
        }}
    }}
    """

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

async def reset_code(card_id: int, email: str):
    if not email:
        raise HTTPException(status_code=400, detail="Email não pode ser vazio")
    import random
    def generate_six_digit_code() -> str:
        return str(random.randint(100000, 999999))
    if not card_id:
        raise HTTPException(status_code=400, detail="ID do cartão não pode ser vazio")
    
    code = generate_six_digit_code()

    template = f"""<!-- TEMPLATE PADRÃO UNYLEYA – CÓDIGO DE REDEFINIÇÃO DE SENHA -->
        <table style="font-family: Arial, sans-serif; color:#333; background-color:#993366; width:100%; border-radius:12px;" border="0" cellspacing="0" cellpadding="0">
        <tr>
            <td align="center">

            <!-- LOGO PRINCIPAL -->
            <p style="margin:2px 0 8px;">
                <img 
                src="https://app.pipefy.com/storage/v1/signed/orgs/55fd8109-fcfb-48e6-a8fc-3238acfa782d/uploads/88f185dd-ba45-4c1c-94c0-614b7b4cabc3/Light%20Logo%20Unyleya.png?signature=Nt%2ByXlzeOzvyniaDoTKnMToOnE9VFB0UgJrYh75zkzw%3D" 
                alt="Logo Unyleya" width="112" height="41" 
                style="display:block;margin:0 auto;">
            </p>

            <!-- FAIXA DE TÍTULO -->
            <table width="85%" style="background-color:#ed7d31;border-radius:12px 12px 0 0;" cellpadding="10">
                <tr>
                <td align="center">
                    <h1 style="margin:0;color:#ffffff;">Código de Redefinição de Senha</h1>
                </td>
                </tr>
            </table>

            <!-- CORPO DO E-MAIL -->
            <table width="85%" style="background-color:#ffffff;border:1px solid #dddddd;border-radius:0 0 12px 12px;margin-bottom:20px;" cellpadding="20">
                <tr>
                <td>

                    <!-- SAUDAÇÃO -->
                    <p style="font-size:16px;">Prezado(a),</p>

                    <!-- CÓDIGO -->
                    <p style="font-size:16px;">Seu código de redefinição de senha é: <strong>{code}</strong></p>

                    <p style="font-size:16px;">Utilize este código para concluir o processo de recuperação de senha. Caso não tenha solicitado, desconsidere este e-mail.</p>

                </td>
                </tr>
            </table>

            </td>
        </tr>
        </table>

        <hr style="margin:20px 0;border:none;border-top:1px solid #dddddd;">

        <!-- RODAPÉ INSTITUCIONAL -->
        <p style="font-family:Arial, sans-serif;font-size:14px;color:#333;">Se precisar de ajuda, responda este e-mail ou escreva para
        <a href="mailto:novos.projetos@unyleya.com.br" style="color:#748396;text-decoration:underline;">novos.projetos@unyleya.com.br</a>.
        </p>

        <p style="font-family:Arial, sans-serif;font-size:16px;color:#ed7d31;font-weight:bold;margin:4px 0;">Novos Projetos</p>
        <p style="font-family:Arial, sans-serif;font-size:12px;color:#833c0b;margin:4px 0;">
        SCN Quadra&nbsp;1, Bloco&nbsp;D, 1º Andar, Sala&nbsp;122 – Brasília/DF
        </p>

        <p style="margin:10px 0;">
        <img 
            src="https://app.pipefy.com/storage/v1/signed/orgs/55fd8109-fcfb-48e6-a8fc-3238acfa782d/uploads/7110d2b1-a536-42bd-97f7-62e6f8ebe3cd/Uny%20logo%20assinatura.png?signature=%2BhJ1DDjGlR6798bRoLmtFmOLywpPYkzC%2BQV2rFQlnnM%3D" 
            alt="Logo Unyleya" width="300">
        </p>

        <p style="color:#748396;font-size:10px;">Este e-mail foi enviado automaticamente.</p>
    """

    # 1. Escapa as aspas internas para usar uma string normal
    escaped_html = template.replace('\n', '').replace('"', '\\"')

    query = f"""
    mutation {{
    createInboxEmail(
        input: {{
        repo_id: 305896989,
        card_id: {card_id},
        from: "novos.projetos@unyleya.com.br",
        fromName: "Novos Projetos - Unyleya",
        to: "{email}",
        subject: "Interface NP - Código de Redefinição de Senha: {code}",
        html: "{escaped_html}"
        }}
    ) {{
        inbox_email {{
        id
        }}
    }}
    }}
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            headers=HEADERS,
            json={"query": query}
        )
        if response.status_code == 200:
            if "Acesso negado" in response.text:
                raise HTTPException(status_code=400, detail="Não foi possivel criar o e-mail no Pipefy. Revise o 'card_id', se realmente existe no pipe")
            email_id = response.json()["data"]["createInboxEmail"]["inbox_email"]["id"]
            if not email_id:
                raise HTTPException(status_code=500, detail="Erro ao criar e-mail no Pipefy, id do e-mail não identificado")

            query_send = f"""
            mutation {{
              sendInboxEmail(input: {{
                id: "{email_id}"
              }}) {{
                success
              }}
            }}
            """
            response_send = await client.post(
                API_URL,
                headers=HEADERS,
                json={"query": query_send}
            )
            if response_send.status_code == 200:
                return {
                    "success": True,
                    "message": "Código enviado com sucesso para o email.",
                    "code": code,
                    "response": response_send.json()
                }
            else:
                raise HTTPException(
                    status_code=response_send.status_code,
                    detail="Erro ao enviar o email: " + response_send.text
                )
            
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail="Erro ao enviar o código: " + response.text
            )

async def forgot_password(email: str):
    # first check if the user exists
    users = await fetch_users_from_pipefy()
    if not users:
        raise HTTPException(status_code=500, detail="Erro ao buscar usuários")
    
    def get_user_by_email(email: str) -> User:
        for user in users.values():
            if user.email == email:
                return user
        return None
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    user_id = user.id
    card_id = user.card_id
    user_password = user.password

    reset_code_response = await reset_code(card_id, email)
    if not reset_code_response.get("success"):
        raise HTTPException(status_code=500, detail="Erro ao enviar o código de redefinição de senha")
    code = reset_code_response.get("code")
    return {
        "success": True,
        "message": "Código de redefinição de senha enviado com sucesso.",
        "code": code,
        "userId": user_id,
        "userPassword": user_password
    }