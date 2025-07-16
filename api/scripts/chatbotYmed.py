from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
import asyncio
from openai import OpenAI
import requests
import logging
from datetime import datetime
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import openai
import json
import uuid
from upstash_redis import Redis
from fastapi import HTTPException

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Verificar se a chave da API está configurada
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logger.error("OPENAI_API_KEY não encontrada nas variáveis de ambiente")
    raise ValueError("OPENAI_API_KEY não configurada")

client = OpenAI(api_key=api_key)
ASSISTANT_ID = "asst_5YTQYHjXL7npoJYTLX3w0cXv"

# Inicializar Redis
redis = Redis.from_env()

class ChatbotMessageRequest(BaseModel):
    message: str
    user_id: str

class ChatbotFeedbackRequest(BaseModel):
    user_id: str
    message_id: str
    rating: int
    feedback: Optional[str] = None

class ConversationMessage(BaseModel):
    id: str
    user_id: str
    message: str
    response: str
    timestamp: datetime
    feedback_rating: Optional[int] = None
    feedback_text: Optional[str] = None

def format_json_as_table(text: str) -> str:
    """
    Converte texto JSON em uma tabela formatada.
    """
    try:
        # Tentar extrair JSON do texto
        import re
        
        # Procurar por blocos JSON no texto
        json_pattern = r'\{.*?\}|\[.*?\]'
        json_matches = re.findall(json_pattern, text, re.DOTALL)
        
        if not json_matches:
            return text
            
        formatted_text = text
        
        for json_str in json_matches:
            try:
                # Tentar fazer parse do JSON
                data = json.loads(json_str)
                
                # Se é uma lista de objetos, criar tabela
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    table = format_dict_list_as_table(data)
                    formatted_text = formatted_text.replace(json_str, table)
                    
                # Se é um objeto simples, criar tabela de propriedades
                elif isinstance(data, dict):
                    table = format_dict_as_table(data)
                    formatted_text = formatted_text.replace(json_str, table)
                    
            except json.JSONDecodeError:
                continue
                
        return formatted_text
        
    except Exception as e:
        logger.error(f"Erro ao formatar tabela: {str(e)}")
        return text

def format_dict_list_as_table(data: List[Dict]) -> str:
    """
    Converte uma lista de dicionários em uma tabela HTML formatada.
    """
    if not data:
        return ""
        
    # Obter todas as chaves únicas
    all_keys = set()
    for item in data:
        all_keys.update(item.keys())
    
    headers = list(all_keys)
    
    # Criar tabela HTML
    table = '<table border="1" style="border-collapse: collapse; width: 100%;">\n'
    
    # Criar cabeçalho
    table += '  <thead>\n    <tr>\n'
    for header in headers:
        table += f'      <th style="padding: 8px; background-color: #f2f2f2;">{header}</th>\n'
    table += '    </tr>\n  </thead>\n'
    
    # Criar corpo da tabela
    table += '  <tbody>\n'
    for item in data:
        table += '    <tr>\n'
        for key in headers:
            value = str(item.get(key, ""))
            table += f'      <td style="padding: 8px;">{value}</td>\n'
        table += '    </tr>\n'
    table += '  </tbody>\n'
    table += '</table>'
        
    return table

def format_dict_as_table(data: Dict) -> str:
    """
    Converte um dicionário em uma tabela HTML de propriedades.
    """
    table = '<table border="1" style="border-collapse: collapse; width: 100%;">\n'
    
    # Criar cabeçalho
    table += '  <thead>\n    <tr>\n'
    table += '      <th style="padding: 8px; background-color: #f2f2f2;">Propriedade</th>\n'
    table += '      <th style="padding: 8px; background-color: #f2f2f2;">Valor</th>\n'
    table += '    </tr>\n  </thead>\n'
    
    # Criar corpo da tabela
    table += '  <tbody>\n'
    for key, value in data.items():
        table += '    <tr>\n'
        table += f'      <td style="padding: 8px;">{key}</td>\n'
        table += f'      <td style="padding: 8px;">{value}</td>\n'
        table += '    </tr>\n'
    table += '  </tbody>\n'
    table += '</table>'
        
    return table

async def process_chatbot_message(message: str, user_id: str) -> Dict[str, Any]:
    try:
        logger.info(f"Processando mensagem via Assistants API para user_id: {user_id}")

        # 1. Criar um thread
        thread_id = await get_or_create_thread_id(user_id)

        # 2. Adicionar a mensagem do usuário
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        # 3. Executar o assistente
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # 4. Aguardar conclusão
        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "cancelled"]:
                raise Exception(f"Assistants API falhou com status: {run_status.status}")
            await asyncio.sleep(2)

        # 5. Recuperar a resposta
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        assistant_messages = [m for m in messages.data if m.role == "assistant"]
        if not assistant_messages:
            raise Exception("Nenhuma resposta recebida do assistente")

        bot_response = assistant_messages[0].content[0].text.value
        
        # Verificar se é uma solicitação de tabela e formatar se necessário
        if is_table_request(message):
            bot_response = format_json_as_table(bot_response)
        
        message_id = str(uuid.uuid4())

        # 6. Salvar no histórico
        await save_message_to_history(user_id, message_id, message, bot_response)

        return {
            "success": True,
            "message_id": message_id,
            "response": bot_response,
            "timestamp": datetime.now().isoformat()
        }

    except openai.OpenAIError as e:
        logger.error(f"Erro da OpenAI (Assistants API): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro da OpenAI: {str(e)}")
    except Exception as e:
        logger.error(f"Erro geral: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")

async def get_or_create_thread_id(user_id: str) -> str:
    cache_key = f"chatbot_thread_{user_id}"
    existing = redis.get(cache_key)
    if existing:
        # Verificar se já é string ou se precisa decodificar
        if isinstance(existing, bytes):
            return existing.decode("utf-8")
        return existing

    # Criar um novo thread
    thread = client.beta.threads.create()
    redis.set(cache_key, thread.id)
    return thread.id

async def get_conversation_history(user_id: str) -> Dict[str, Any]:
    """
    Recupera o histórico de conversas de um usuário.
    """
    try:
        cache_key = f"chatbot_conversation_{user_id}"
        cached_history = redis.json.get(cache_key)
        
        if cached_history:
            return cached_history[0]
        
        return {
            "user_id": user_id,
            "messages": [],
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)}")

async def clear_conversation_history(user_id: str) -> Dict[str, Any]:
    """
    Limpa o histórico de conversas de um usuário.
    """
    try:
        cache_key = f"chatbot_conversation_{user_id}"
        redis.json.delete(cache_key)
        
        return {
            "success": True,
            "message": "Histórico de conversa limpo com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar histórico: {str(e)}")

async def save_message_to_history(user_id: str, message_id: str, message: str, response: str):
    """
    Salva uma mensagem no histórico de conversas.
    """
    try:
        cache_key = f"chatbot_conversation_{user_id}"
        
        # Buscar histórico existente
        existing_history = await get_conversation_history(user_id)
        
        # Adicionar nova mensagem
        new_message = {
            "id": message_id,
            "message": message,
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "feedback_rating": None,
            "feedback_text": None
        }
        
        existing_history["messages"].append(new_message)
        
        # Manter apenas as últimas 50 mensagens
        if len(existing_history["messages"]) > 50:
            existing_history["messages"] = existing_history["messages"][-50:]
        
        # Salvar no Redis
        redis.json.set(cache_key, path="$", value=existing_history)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar mensagem: {str(e)}")

async def submit_feedback(user_id: str, message_id: str, rating: int, feedback: Optional[str] = None) -> Dict[str, Any]:
    """
    Submete feedback para uma mensagem específica.
    """
    try:
        cache_key = f"chatbot_conversation_{user_id}"
        conversation_history = await get_conversation_history(user_id)
        
        # Encontrar e atualizar a mensagem específica
        for message in conversation_history["messages"]:
            if message["id"] == message_id:
                message["feedback_rating"] = rating
                message["feedback_text"] = feedback
                break
        else:
            raise HTTPException(status_code=404, detail="Mensagem não encontrada")
        
        # Salvar histórico atualizado
        redis.json.set(cache_key, path="$", value=conversation_history)
        
        # Salvar feedback separadamente para análise
        feedback_key = f"chatbot_feedback_{message_id}"
        feedback_data = {
            "user_id": user_id,
            "message_id": message_id,
            "rating": rating,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat()
        }
        redis.json.set(feedback_key, path="$", value=feedback_data)
        
        return {
            "success": True,
            "message": "Feedback enviado com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar feedback: {str(e)}")

def is_table_request(message: str) -> bool:
    palavras_chave = ["tabela", "coloque em tabela", "comparação", "listar", "formato de tabela", "colunas"]
    return any(p in message.lower() for p in palavras_chave)