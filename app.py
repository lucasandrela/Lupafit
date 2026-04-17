from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from auth import gerar_token, token_obrigatorio
from flask_cors import CORS
import os 
from dotenv import load_dotenv
import json
import re

load_dotenv()

app = Flask(__name__)
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

# --- Função Auxiliar ---
def limpar_cpf(cpf):
    return "".join(filter(str.isdigit, str(cpf)))

# --- Rotas ---

@app.route('/', methods=['GET'])
def root():
    return jsonify({"api": "API Catraca Academia", "version": "1.1", "author": "Lucas Assis"}), 200

@app.route('/login', methods=['POST'])
def login():
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Dados de login ausentes."}), 400
    
    usuario = dados.get("usuario")
    senha = dados.get("senha")

    if usuario == ADM_USUARIO and senha == ADM_SENHA:
        token = gerar_token(usuario)
        return jsonify({"message": "Login bem-sucedido.", "token": token}), 200
    
    return jsonify({"error": "Credenciais inválidas."}), 401

@app.route('/usuarios', methods=['GET'])
@token_obrigatorio
def listar_usuarios():
    try:
        usuarios_ref = db.collection('usuarios_catraca')
        docs = usuarios_ref.stream()
        usuarios = []
        for doc in docs:
            usuario = doc.to_dict()
            usuario["id"] = doc.id
            usuarios.append(usuario)
        return jsonify(usuarios), 200
    except Exception as e:
        return jsonify({"error": "Falha ao listar usuários."}), 500

@app.route("/usuarios", methods=["POST"])
@token_obrigatorio
def cadastrar_usuario():
    dados = request.get_json()
    if not dados or "nome" not in dados or "cpf" not in dados or "ativo" not in dados:
        return jsonify({"error": "Dados inválidos. 'nome', 'cpf' e 'ativo' são obrigatórios."}), 400
    
    cpf_limpo = limpar_cpf(dados["cpf"])
    if len(cpf_limpo) != 11:
        return jsonify({"error": "CPF deve conter 11 dígitos."}), 400

    try:
        # Verifica se CPF já existe
        existente = db.collection('usuarios_catraca').where("cpf", "==", cpf_limpo).limit(1).get()
        if existente:
            return jsonify({"error": "CPF já cadastrado."}), 409

        db.collection('usuarios_catraca').add({
            "nome": dados["nome"],
            "cpf": cpf_limpo,
            "ativo": dados["ativo"],
            "esta_dentro": False
        })
        return jsonify({"message": "Usuário cadastrado com sucesso."}), 201
    except Exception as e:
        return jsonify({"error": "Falha no cadastro."}), 400

@app.route('/usuarios/<id_ou_cpf>', methods=['DELETE'])
@token_obrigatorio
def excluir_usuario(id_ou_cpf):
    try:
        # Tenta excluir por ID do documento ou por CPF
        doc_ref = db.collection('usuarios_catraca').document(id_ou_cpf)
        if doc_ref.get().exists:
            doc_ref.delete()
            return jsonify({"message": "Usuário excluído com sucesso."}), 200
        
        # Se não achou por ID, tenta por CPF
        docs = db.collection('usuarios_catraca').where("cpf", "==", id_ou_cpf).get()
        for doc in docs:
            db.collection('usuarios_catraca').document(doc.id).delete()
            return jsonify({"message": "Usuário excluído com sucesso."}), 200

        return jsonify({"error": "Usuário não encontrado."}), 404
    except Exception as e:
        return jsonify({"error": "Falha na exclusão."}), 400

@app.route('/usuarios/<id_ou_cpf>', methods=['PUT', 'PATCH'])
@token_obrigatorio
def editar_usuario(id_ou_cpf):
    dados = request.get_json()
    try:
        doc_ref = db.collection('usuarios_catraca').document(id_ou_cpf)
        if not doc_ref.get().exists:
            # Se não achou por ID, tenta buscar pelo campo CPF
            docs = db.collection('usuarios_catraca').where("cpf", "==", id_ou_cpf).limit(1).get()
            if not docs:
                return jsonify({"error": "Usuário não encontrado."}), 404
            doc_ref = db.collection('usuarios_catraca').document(docs[0].id)
        
        if "cpf" in dados:
            dados["cpf"] = limpar_cpf(dados["cpf"])

        doc_ref.update(dados)
        return jsonify({"message": "Usuário atualizado com sucesso."}), 200
    except Exception as e:
        return jsonify({"error": "Falha na atualização."}), 400

@app.route('/catraca/validar', methods=['POST'])
def validar_acesso():
    dados = request.get_json()
    cpf_inserido = limpar_cpf(dados.get("cpf", ""))

    if not cpf_inserido:
        return jsonify({"error": "CPF é obrigatório."}), 400

    docs = db.collection('usuarios_catraca').where("cpf", "==", cpf_inserido).limit(1).get()
    
    if not docs:
        return jsonify({"status": "negado", "mensagem": "CPF não cadastrado"}), 404

    usuario = docs[0].to_dict()
    if not usuario.get("ativo", False):
        return jsonify({"status": "bloqueado", "mensagem": "Procure a secretaria da academia"}), 403

    return jsonify({
        "status": "liberado",
        "mensagem": f"Bem-vindo(a), {usuario.get('nome')}!",
        "liberar_trava": True
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Rota não encontrada."}), 404

if __name__ == '__main__':
    app.run(debug=True)