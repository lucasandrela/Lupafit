from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from auth import gerar_token, token_obrigatorio
from flask_cors import CORS
import os 
from dotenv import load_dotenv
import json
from flasgger import Swagger
import re

load_dotenv()

app = Flask(__name__)
app.config['SWAGGER'] = {'openapi': '3.0.3'}
swagger = Swagger(app, template_file='openapi.yaml')

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
CORS(app, origins="*")

ADM_USUARIO = os.getenv("ADM_USUARIO")
ADM_SENHA = os.getenv("ADM_SENHA")

# Inicialização do Firebase
if os.getenv("VERCEL"):
    cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))
else:
    cred = credentials.Certificate("firebase.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Funções Auxiliares ---

def limpar_e_validar_cpf(cpf):
    """Remove caracteres não numéricos e valida tamanho"""
    cpf_limpo = re.sub(r'\D', '', str(cpf))
    if len(cpf_limpo) != 11:
        return None
    return cpf_limpo

# --- Rotas de Autenticação ---

@app.route('/login', methods=['POST'])
def login():
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Dados ausentes."}), 400
    
    usuario = dados.get("usuario")
    senha = dados.get("senha")

    if usuario == ADM_USUARIO and senha == ADM_SENHA:
        token = gerar_token(usuario)
        return jsonify({"message": "Login ok.", "token": token}), 200
    
    return jsonify({"error": "Credenciais inválidas."}), 401

# --- Rotas da Catraca (Fluxo de Entrada e Saída) ---

@app.route('/catraca/entrada', methods=['POST'])
def entrada_academia():
    dados = request.get_json()
    cpf_bruto = dados.get("cpf")
    cpf_limpo = limpar_e_validar_cpf(cpf_bruto)

    if not cpf_limpo:
        return jsonify({"status": "erro", "mensagem": "CPF deve ter 11 dígitos"}), 400

    docs = db.collection('usuarios_catraca').where("cpf", "==", cpf_limpo).limit(1).get()
    
    if not docs:
        return jsonify({"status": "negado", "mensagem": "CPF não cadastrado"}), 404

    usuario_ref = db.collection('usuarios_catraca').document(docs[0].id)
    usuario = docs[0].to_dict()

    # Validação 1: Cadastro Ativo
    if not usuario.get("ativo", False):
        return jsonify({"status": "bloqueado", "mensagem": "Procure a secretaria da academia"}), 403

    # Validação 2: Anti-Passback (Já está dentro?)
    if usuario.get("esta_dentro", False):
        return jsonify({"status": "bloqueado", "mensagem": "Usuário já está na academia"}), 403

    # Sucesso: Atualiza status e libera
    usuario_ref.update({"esta_dentro": True})
    return jsonify({
        "status": "liberado", 
        "mensagem": f"Bem-vindo, {usuario.get('nome')}!", 
        "liberar_trava": True
    }), 200

@app.route('/catraca/saida', methods=['POST'])
def saida_academia():
    dados = request.get_json()
    cpf_bruto = dados.get("cpf")
    cpf_limpo = limpar_e_validar_cpf(cpf_bruto)

    if not cpf_limpo:
        return jsonify({"status": "erro", "mensagem": "CPF inválido"}), 400

    docs = db.collection('usuarios_catraca').where("cpf", "==", cpf_limpo).limit(1).get()
    
    if not docs:
        return jsonify({"status": "negado", "mensagem": "CPF não cadastrado"}), 404

    usuario_ref = db.collection('usuarios_catraca').document(docs[0].id)
    usuario = docs[0].to_dict()

    # Saída sempre libera e reseta o status de permanência
    usuario_ref.update({"esta_dentro": False})
    return jsonify({
        "status": "liberado", 
        "mensagem": f"Até logo, {usuario.get('nome')}!", 
        "liberar_trava": True
    }), 200

# --- Rotas da Secretaria (Gestão de Usuários) ---

@app.route("/usuarios", methods=["POST"])
@token_obrigatorio
def cadastrar_aluno():
    dados = request.get_json()
    cpf_limpo = limpar_e_validar_cpf(dados.get("cpf"))

    if not cpf_limpo:
        return jsonify({"error": "CPF deve ter 11 dígitos numéricos."}), 400
    
    if "nome" not in dados or "ativo" not in dados:
        return jsonify({"error": "Nome e status ativo (boolean) são obrigatórios."}), 400

    # Evitar duplicados
    existente = db.collection('usuarios_catraca').where("cpf", "==", cpf_limpo).limit(1).get()
    if existente:
        return jsonify({"error": "Este CPF já está cadastrado."}), 409

    try:
        db.collection('usuarios_catraca').add({
            "nome": dados["nome"],
            "cpf": cpf_limpo,
            "ativo": dados["ativo"],
            "esta_dentro": False  # Todo aluno começa do lado de fora
        })
        return jsonify({"message": "Aluno cadastrado com sucesso!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/usuarios/<cpf>", methods=["PATCH"])
@token_obrigatorio
def atualizar_status_secretaria(cpf):
    """Permite à secretaria alterar 'ativo' ou resetar 'esta_dentro'"""
    dados = request.get_json()
    docs = db.collection('usuarios_catraca').where("cpf", "==", cpf).limit(1).get()
    
    if not docs:
        return jsonify({"error": "Usuário não encontrado."}), 404

    doc_ref = db.collection('usuarios_catraca').document(docs[0].id)
    
    campos_update = {}
    if "ativo" in dados: campos_update["ativo"] = dados["ativo"]
    if "esta_dentro" in dados: campos_update["esta_dentro"] = dados["esta_dentro"]
    if "nome" in dados: campos_update["nome"] = dados["nome"]

    doc_ref.update(campos_update)
    return jsonify({"message": "Dados atualizados pela secretaria."}), 200

if __name__ == '__main__':
    app.run(debug=True)