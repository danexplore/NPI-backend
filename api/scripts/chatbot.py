from flask import Flask, request, jsonify
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

openai = OpenAI(api_key=api_key)
client = OpenAI(api_key=openai.api_key)

# Configuração do OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Inicializar Redis
redis = Redis.from_env()

app = Flask(__name__)
CORS(app)  # Permitir requisições do frontend

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

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint para verificar se o servidor está funcionando"""
    logger.info("Health check solicitado")
    return jsonify({
        "status": "ok", 
        "message": "Servidor funcionando",
        "timestamp": str(datetime.now()) if 'datetime' in globals() else "N/A"
    })

@app.route("/chatbot", methods=["POST"])
def chatbot():
    logger.info("Requisição recebida no endpoint /chatbot")
    
    try:
        # Verificar se o request tem JSON
        if not request.is_json:
            logger.warning("Request não tem Content-Type application/json")
            return jsonify({"error": "Content-Type deve ser application/json"}), 400
        
        data = request.get_json()
        if not data:
            logger.warning("Dados JSON inválidos ou vazios")
            return jsonify({"error": "Dados JSON inválidos"}), 400
        
        page_content = data.get("pageContent", "").strip()
        question = data.get("question", "").strip()

        logger.info(f"Pergunta recebida: {question[:50]}...")
        logger.info(f"Conteúdo da página: {len(page_content)} caracteres")

        if not page_content:
            logger.warning("Conteúdo da página vazio")
            return jsonify({"error": "Conteúdo da página é obrigatório"}), 400
        
        if not question:
            logger.warning("Pergunta vazia")
            return jsonify({"error": "Pergunta é obrigatória"}), 400

        # Verificar se a pergunta não é muito longa
        if len(question) > 500:
            logger.warning(f"Pergunta muito longa: {len(question)} caracteres")
            return jsonify({"error": "Pergunta muito longa (máximo 500 caracteres)"}), 400

        logger.info("Enviando requisição para OpenAI...")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Você é um assistente especializado em análise de propostas de cursos universitários. 
                    Responda perguntas de forma clara e objetiva com base no conteúdo fornecido.
                    Se a pergunta não puder ser respondida com base no conteúdo, informe isso educadamente.
                    Mantenha suas respostas concisas e relevantes."""
                },
                {
                    "role": "user",
                    "content": f"Conteúdo da página:\n{page_content}\n\nPergunta: {question}"
                }
            ],
            max_tokens=500,
            temperature=0.7
        )

        if not response.choices or not response.choices[0].message.content:
            logger.error("Resposta vazia da OpenAI")
            return jsonify({"error": "Resposta vazia da OpenAI"}), 500

        answer = response.choices[0].message.content.strip()
        logger.info(f"Resposta gerada com sucesso: {len(answer)} caracteres")

        return jsonify({"response": answer})
    
    except Exception as e:
        logger.error(f"Erro no chatbot: {str(e)}")
        traceback.print_exc()
        
        # Diferentes tipos de erro
        if "rate limit" in str(e).lower():
            return jsonify({"error": "Limite de uso da API excedido. Tente novamente em alguns minutos."}), 429
        elif "timeout" in str(e).lower():
            return jsonify({"error": "Timeout na requisição. Tente novamente."}), 408
        elif "api key" in str(e).lower():
            return jsonify({"error": "Problema com a configuração da API"}), 500
        else:
            return jsonify({"error": f"Erro interno do servidor: {str(e)}"}), 500

async def process_chatbot_message(message: str, user_id: str) -> Dict[str, Any]:
    """
    Processa uma mensagem do chatbot e retorna a resposta.
    """
    try:
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
        
        Responda de forma útil, profissional e concisa.
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
        
        # Fazer chamada para OpenAI
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message.content
        
        # Salvar conversa no histórico
        message_id = str(uuid.uuid4())
        await save_message_to_history(user_id, message_id, message, bot_response)
        
        return {
            "success": True,
            "message_id": message_id,
            "response": bot_response,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
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

if __name__ == "__main__":
    logger.info("Iniciando servidor Flask na porta 5000...")
    logger.info("Acesse http://localhost:5000/health para verificar o status")
    app.run(debug=True, port=5000, host='0.0.0.0')