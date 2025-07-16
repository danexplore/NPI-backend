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

async def test_chatbot():
    """
    Função para testar o chatbot via prompt de comando.
    """
    print("=== Testador do Chatbot Y-med ===")
    print("Comandos disponíveis:")
    print("- Digite uma mensagem para conversar")
    print("- Digite 'historico' para ver o histórico")
    print("- Digite 'limpar' para limpar o histórico")
    print("- Digite 'sair' para encerrar")
    print("=" * 40)
    
    user_id = "test_user"
    
    while True:
        try:
            user_input = input("\nVocê: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == 'sair':
                print("Encerrando o teste...")
                break
                
            elif user_input.lower() == 'historico':
                history = await get_conversation_history(user_id)
                print("\n=== Histórico de Conversas ===")
                if not history["messages"]:
                    print("Nenhuma conversa encontrada.")
                else:
                    for i, msg in enumerate(history["messages"], 1):
                        print(f"\n{i}. Você: {msg['message']}")
                        print(f"   Bot: {msg['response']}")
                        print(f"   Horário: {msg['timestamp']}")
                        if msg.get('feedback_rating'):
                            print(f"   Avaliação: {msg['feedback_rating']}/5")
                continue
                
            elif user_input.lower() == 'limpar':
                await clear_conversation_history(user_id)
                print("Histórico limpo com sucesso!")
                continue
            
            # Processar mensagem normal
            print("Bot está pensando...")
            response = await process_chatbot_message(user_input, user_id)
            
            print(f"\nBot: {response['response']}")
            
            # Opção de feedback
            feedback_input = input("\nDeseja avaliar esta resposta? (s/n): ").strip().lower()
            if feedback_input == 's':
                try:
                    rating = int(input("Avaliação de 1 a 5: "))
                    if 1 <= rating <= 5:
                        feedback_text = input("Comentário (opcional): ").strip()
                        await submit_feedback(user_id, response['message_id'], rating, feedback_text or None)
                        print("Feedback enviado com sucesso!")
                    else:
                        print("Avaliação deve ser entre 1 e 5.")
                except ValueError:
                    print("Avaliação inválida.")
            
        except KeyboardInterrupt:
            print("\n\nEncerrando o teste...")
            break
        except Exception as e:
            print(f"Erro: {str(e)}")
            print("Tente novamente.")

if __name__ == "__main__":
    print("Iniciando teste do chatbot...")
    try:
        asyncio.run(test_chatbot())
    except KeyboardInterrupt:
        print("\nTeste interrompido pelo usuário.")
    except Exception as e:
        print(f"Erro ao iniciar teste: {str(e)}")