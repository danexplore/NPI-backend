from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import traceback
from openai import OpenAI
import requests

load_dotenv()

openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
client = OpenAI(api_key=openai.api_key)

app = Flask(__name__)
CORS(app)  # Permitir requisições do frontend

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json()
    page_content = data.get("pageContent", "").strip()
    question = data.get("question", "").strip()

    if not page_content or not question:
        print("Conteúdo da página ou pergunta estão vazios")
        return jsonify({"error": "Dados incompletos"}), 400

    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Você é um assistente especializado em análise de propostas de cursos universitários. 
                    Responda perguntas de forma clara e objetiva com base no conteúdo fornecido.
                    Se a pergunta não puder ser respondida com base no conteúdo, informe isso educadamente."""
                },
                {
                    "role": "user",
                    "content": f"Conteúdo da página:\n{page_content}\n\nPergunta: {question}"
                }
            ],
            max_tokens=500,
            temperature=0.7
        )

        return jsonify({"response": response.choices[0].message.content})
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)