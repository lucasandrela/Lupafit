from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from auth import gerar_token, token_obrigatorio
from flask_cors import CORS
import os 
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
CORS(app, origins="*")

ADM_USUARIO = os.getenv("ADM_USUARIO")
ADM_SENHA = os.getenv("ADM_SENHA")

if os.getenv("VERCEL"):
    cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_CREDENTIALS")))
else:
    cred = credentials.Certificate("firebase.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

@app.route('/', methods=['GET'])
def root():
    return jsonify({"api": "API Catraca Academia", "version": "1.0", "author": "Lucas Assis"}), 200

@app.route('/excluir_usuario/<usuario_id>', methods=['DELETE'])
@token_obrigatorio
def excluir_usuario(usuario_id):
    try:
        usuario_ref = db.collection('usuarios_catraca').document(usuario_id)
        if not usuario_ref.get().exists:
            return jsonify({"error": "Usuário não encontrado."}), 404

        usuario_ref.delete()
        return jsonify({"message": "Usuário excluído com sucesso!."}), 200
    except Exception as e:
        return jsonify({"error": "Falha na exclusão."}), 400

@app.route('/editar_usuario/<usuario_id>', methods=['PUT'])
@token_obrigatorio
def editar_usuario(usuario_id):
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Dados de atualização ausentes."}), 400
    
    try:
        usuario_ref = db.collection('usuarios_catraca').document(usuario_id)
        if not usuario_ref.get().exists:
            return jsonify({"error": "Usuário não encontrado."}), 404
        
        usuario_ref.update(dados)
        return jsonify({"message": "Usuário atualizado com sucesso!."}), 200
    except Exception as e:
        return jsonify({"error": "Falha na atualização."}), 400

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



# Na rota /catraca/validar, altere a busca para:
@app.route('/catraca/validar', methods=['POST'])
def validar_acesso():
    dados = request.get_json()
    cpf_bruto = dados.get("cpf", "")
    # Garante que estamos tratando apenas números
    cpf_inserido = "".join(filter(str.isdigit, str(cpf_bruto)))

    if not cpf_inserido:
        return jsonify({"error": "CPF é obrigatório."}), 400

    # Busca no Firestore
    docs = db.collection('usuarios_catraca').where("cpf", "==", cpf_inserido).limit(1).get()
    
    if len(docs) == 0: # Forma mais segura de verificar se existe
        return jsonify({"status": "negado", "mensagem": "CPF não cadastrado"}), 404

    usuario = docs[0].to_dict()
    esta_ativo = usuario.get("ativo", False)

    if esta_ativo:
        return jsonify({
            "status": "liberado",
            "mensagem": f"Bem-vindo(a), {usuario.get('nome')}!",
            "liberar_trava": True
        }), 200
    else:
        return jsonify({
            "status": "bloqueado",
            "mensagem": "Procure a secretaria da academia"
        }), 403


@app.route("/usuarios", methods=["POST"])
@token_obrigatorio
def post_usuario():
    dados = request.get_json()
    if not dados or "nome" not in dados or "cpf" not in dados or "ativo" not in dados:
        return jsonify({"error": "Dados inválidos. 'nome', 'cpf' e 'ativo' (bool) são obrigatórios."}), 400
    
    try:
        db.collection('usuarios_catraca').add({
            "nome": dados["nome"],
            "cpf": dados["cpf"],
            "ativo": dados["ativo"]
        })
        return jsonify({"message": "Usuário cadastrado com sucesso!."}), 201
    except Exception as e:
        return jsonify({"error": "Falha no cadastro."}), 400



@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Rota não encontrada."}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Erro interno do servidor."}), 500

if __name__ == '__main__':
    app.run(debug=True)