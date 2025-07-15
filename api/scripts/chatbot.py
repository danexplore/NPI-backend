from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
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

async def process_chatbot_message(message: str, user_id: str) -> Dict[str, Any]:
    """
    Processa uma mensagem do chatbot e retorna a resposta.
    """
    try:
        logger.info(f"Processando mensagem para user_id: {user_id}")
        
        # Verificar se a chave da API está configurada
        if not api_key:
            logger.error("OPENAI_API_KEY não configurada")
            raise HTTPException(status_code=500, detail="Chave da API OpenAI não configurada")
        
        # Buscar histórico de conversas do usuário
        conversation_history = await get_conversation_history(user_id)
        
        # Preparar contexto para o ChatGPT
        system_prompt = """
        Você é um assistente virtual especializado em cursos e educação da Unyleya. 
        Você pode ajudar com informações sobre:
        - Cursos disponíveis
        - Processo de aprovação de cursos
        - Coordenadores e responsáveis
        - Status de propostas
        - Informações gerais sobre a plataforma
        - Dúvidas frequentes
        - Respostas a perguntas comuns dos usuários
 
        Se o usuário fizer uma pergunta fora do seu escopo, responda de forma educada e sugira que ele entre em contato com o suporte ou consulte a documentação.
        Mantenha um tom profissional e amigável.
        Se o usuário pedir uma tabela ou lista, forneça uma resposta estruturada e bem formatada. Exemplo:
        | Instituição   | Curso                                       | Modalidade   | Duração    | Valor (R$) |
        |---------------|---------------------------------------------|--------------|------------|------------|
        | Instituição A | Pós-graduação em Cibersegurança             | EAD          | 18 meses   | 9.000      |
        | Instituição B | Especialização em Segurança da Informação   | Presencial   | 12 meses   | 8.500      |
        | Instituição C | MBA em Cibersegurança e Proteção de Dados   | EAD          | 24 meses   | 10.500     |
        | Instituição D | Gestão de Riscos Cibernéticos               | Presencial   | 16 meses   | 7.800      |
        | Instituição E | Certificação em Cibersegurança              | EAD          | 8 meses    | 5.000      |
        
        Responda de forma útil, profissional e concisa. Se você não tiver informações específicas sobre algo, seja honesto sobre isso.
        """
        
        # Construir mensagens para o ChatGPT
        messages = [{"role": "system", "content": system_prompt}]
        
        # Adicionar histórico recente (últimas 10 mensagens)
        recent_history = conversation_history.get("messages", [])[-10:]
        for msg in recent_history:
            messages.append({"role": "user", "content": msg["message"]})
            messages.append({"role": "assistant", "content": msg["response"]})
        
        # Adicionar mensagem atual
        messages.append({"role": "user", "content": message})
        
        logger.info(f"Fazendo chamada para OpenAI com {len(messages)} mensagens")
        
        # Fazer chamada para OpenAI usando a nova API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message.content
        logger.info(f"Resposta recebida da OpenAI: {len(bot_response)} caracteres")
        
        # Salvar conversa no histórico
        message_id = str(uuid.uuid4())
        await save_message_to_history(user_id, message_id, message, bot_response)
        
        return {
            "success": True,
            "message_id": message_id,
            "response": bot_response,
            "timestamp": datetime.now().isoformat()
        }
        
    except openai.OpenAIError as e:
        logger.error(f"Erro da OpenAI: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro da OpenAI: {str(e)}")
    except Exception as e:
        logger.error(f"Erro geral ao processar mensagem: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {str(e)}")

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