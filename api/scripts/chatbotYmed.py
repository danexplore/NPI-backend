import os
from dotenv import load_dotenv
import asyncio
from openai import OpenAI
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

class ConversationMessage(BaseModel):
    id: str
    user_id: str
    message: str
    response: str
    timestamp: datetime

def format_json_as_table(text: str) -> str:
    """
    Converte texto JSON em uma tabela formatada.
    """
    try:
        import re
        
        # Primeiro, tentar limpar e corrigir o JSON
        cleaned_text = clean_json_text(text)
        
        # Procurar por estruturas JSON válidas
        json_pattern = r'\{[^{}]*"tabela"[^{}]*:\s*\[[^\]]*\]\s*\}'
        json_matches = re.findall(json_pattern, cleaned_text, re.DOTALL)
        
        if not json_matches:
            # Fallback: procurar por arrays JSON simples
            json_pattern = r'\[[^\[\]]*\{[^{}]*\}[^\[\]]*\]'
            json_matches = re.findall(json_pattern, cleaned_text, re.DOTALL)
        
        if not json_matches:
            return text
            
        formatted_text = text
        
        for json_str in json_matches:
            try:
                # Tentar fazer parse do JSON
                data = json.loads(json_str)
                
                # Se tem propriedade "tabela", usar essa
                if isinstance(data, dict) and "tabela" in data:
                    table_data = data["tabela"]
                    if isinstance(table_data, list) and table_data:
                        table = format_dict_list_as_table(table_data)
                        formatted_text = formatted_text.replace(json_str, table)
                        
                # Se é uma lista de objetos diretamente
                elif isinstance(data, list) and data and isinstance(data[0], dict):
                    table = format_dict_list_as_table(data)
                    formatted_text = formatted_text.replace(json_str, table)
                    
            except json.JSONDecodeError as e:
                logger.error(f"Erro ao fazer parse do JSON: {str(e)}")
                # Tentar extrair dados manualmente
                manual_data = extract_data_manually(json_str)
                if manual_data:
                    table = format_dict_list_as_table(manual_data)
                    formatted_text = formatted_text.replace(json_str, table)
                continue
                
        return formatted_text
        
    except Exception as e:
        logger.error(f"Erro ao formatar tabela: {str(e)}")
        return text

def clean_json_text(text: str) -> str:
    """
    Limpa e corrige problemas comuns em JSON malformado.
    """
    import re
    
    # Remover caracteres estranhos antes e depois do JSON
    text = re.sub(r'^[^{[]*', '', text)
    text = re.sub(r'[^}\]]*$', '', text)
    
    # Corrigir vírgulas extras
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    
    # Corrigir aspas
    text = re.sub(r'([{,]\s*)(\w+):', r'\1"\2":', text)
    
    return text

def extract_data_manually(text: str) -> List[Dict]:
    """
    Extrai dados de tabela manualmente quando o JSON está malformado.
    """
    try:
        import re
        
        # Procurar por padrões como "key": "value"
        pattern = r'"([^"]+)":\s*"([^"]*)"'
        matches = re.findall(pattern, text)
        
        if not matches:
            return []
            
        # Agrupar matches em objetos
        objects = []
        current_obj = {}
        
        for key, value in matches:
            current_obj[key] = value
            
            # Se encontramos um conjunto completo de propriedades, criar novo objeto
            if len(current_obj) >= 5:  # Assumindo pelo menos 5 propriedades por objeto
                objects.append(current_obj.copy())
                current_obj = {}
        
        # Adicionar último objeto se não estiver vazio
        if current_obj:
            objects.append(current_obj)
            
        return objects
        
    except Exception as e:
        logger.error(f"Erro na extração manual: {str(e)}")
        return []

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
    
    headers = sorted(list(all_keys))  # Ordenar para consistência
    
    # Criar tabela HTML
    table = '<table border="1" style="border-collapse: collapse; width: 100%; margin: 10px 0;">\n'
    
    # Criar cabeçalho
    table += '  <thead>\n    <tr>\n'
    for header in headers:
        table += f'      <th style="padding: 12px; background-color: #f2f2f2; text-align: left; font-weight: bold;">{header}</th>\n'
    table += '    </tr>\n  </thead>\n'
    
    # Criar corpo da tabela
    table += '  <tbody>\n'
    for i, item in enumerate(data):
        bg_color = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        table += f'    <tr style="background-color: {bg_color};">\n'
        for key in headers:
            value = str(item.get(key, ""))
            # Se o valor contém URL, criar link
            if value.startswith("http"):
                value = f'<a href="{value}" target="_blank">{value}</a>'
            table += f'      <td style="padding: 12px; border: 1px solid #ddd;">{value}</td>\n'
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
            assistant_id=ASSISTANT_ID,
            max_completion_tokens=2500,
            temperature=1.0
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
            "timestamp": datetime.now().isoformat()
        }
        
        existing_history["messages"].append(new_message)
        
        # Manter apenas as últimas 50 mensagens
        if len(existing_history["messages"]) > 50:
            existing_history["messages"] = existing_history["messages"][-50:]
        
        # Salvar no Redis
        redis.json.set(cache_key, path="$", value=existing_history)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar mensagem: {str(e)}")

def is_table_request(message: str) -> bool:
    palavras_chave = ["tabela", "coloque em tabela", "comparação", "listar", "formato de tabela", "colunas"]
    return any(p in message.lower() for p in palavras_chave)

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
                continue
                
            elif user_input.lower() == 'limpar':
                await clear_conversation_history(user_id)
                print("Histórico limpo com sucesso!")
                continue
            
            # Processar mensagem normal
            print("Bot está pensando...")
            response = await process_chatbot_message(user_input, user_id)
            
            print(f"\nBot: {response['response']}")
            
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