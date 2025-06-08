import asyncio
import os
import shutil
import uuid
import sqlite3
import random
import string
from fastapi import Request
from fastapi import FastAPI, HTTPException, UploadFile, Form, File, WebSocket, WebSocketDisconnect, Path, BackgroundTasks
from pydantic import BaseModel, EmailStr, field_validator
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal
from models import SessionLocal, Message
from datetime import datetime
from fastapi import Query


from fastapi.staticfiles import StaticFiles





app = FastAPI()
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
DB_FILE = "usuarios.db"

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialização do banco
def inicializar_banco():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS salas (
                codigo TEXT PRIMARY KEY,
                email_professor TEXT UNIQUE,
                FOREIGN KEY (email_professor) REFERENCES usuarios(email)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                cargo TEXT CHECK(cargo IN ('professor', 'aluno')) NOT NULL,
                sala TEXT,
                FOREIGN KEY (sala) REFERENCES salas(codigo)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS publicacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aluno INTEGER NOT NULL,
                codigo_sala TEXT NOT NULL,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                imagem TEXT,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aluno) REFERENCES usuarios(id),
                FOREIGN KEY (codigo_sala) REFERENCES salas(codigo)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remetente TEXT NOT NULL,
                destinatario TEXT NOT NULL,
                mensagem TEXT NOT NULL,
                lida INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (remetente) REFERENCES usuarios(email),
                FOREIGN KEY (destinatario) REFERENCES usuarios(email)
            )
        """)

        conn.commit()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS salas (
                codigo TEXT PRIMARY KEY,
                email_professor TEXT UNIQUE,
                FOREIGN KEY (email_professor) REFERENCES usuarios(email)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                cargo TEXT CHECK(cargo IN ('professor', 'aluno')) NOT NULL,
                sala TEXT,
                FOREIGN KEY (sala) REFERENCES salas(codigo)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS publicacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aluno INTEGER NOT NULL,
                codigo_sala TEXT NOT NULL,
                tipo TEXT NOT NULL,
                titulo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                imagem TEXT,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aluno) REFERENCES usuarios(id),
                FOREIGN KEY (codigo_sala) REFERENCES salas(codigo)
            )
        """)
        cursor.execute("PRAGMA table_info(publicacoes)")
        colunas = [col[1] for col in cursor.fetchall()]
        if "nota" not in colunas:
            cursor.execute("ALTER TABLE publicacoes ADD COLUMN nota REAL DEFAULT NULL")


        conn.commit()

@app.on_event("startup")
def startup_event():
    inicializar_banco()

# Modelos
class Usuario(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    cargo: Literal['professor', 'aluno']
    sala: str | None = None

    @field_validator("senha")
    def senha_minima(cls, v):
        if len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        return v


class LoginRequest(BaseModel):
    identificador: str  # pode ser email ou nome
    senha: str



class Publicacao(BaseModel):
    email_aluno: EmailStr
    codigo_sala: str
    tipo: Literal["podcast", "fotografia", "tematica"]
    titulo: str
    conteudo: str
    imagem: UploadFile = File(None)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: int):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: int):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_personal_message(self, message: str, client_id: int):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

    async def send_user_list(self):
        user_list = list(self.active_connections.keys())
        for ws in self.active_connections.values():
            await ws.send_text(f"[USER_LIST] {user_list}")

    
manager = ConnectionManager()



# Função para gerar código de sala
def gerar_codigo_sala():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# Rota: Cadastro de usuário
@app.post("/cadastrar")
def cadastrar_usuario(usuario: Usuario):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            codigo_sala = None

            if usuario.cargo == "professor":
                while True:
                    codigo_sala = gerar_codigo_sala()
                    cursor.execute("SELECT 1 FROM salas WHERE codigo = ?", (codigo_sala,))
                    if not cursor.fetchone():
                        break

                cursor.execute(
                    "INSERT INTO salas (codigo, email_professor) VALUES (?, ?)",
                    (codigo_sala, usuario.email)
                )

            elif usuario.cargo == "aluno":
                if not usuario.sala:
                    raise HTTPException(status_code=400, detail="Alunos devem informar o código da sala.")
                cursor.execute("SELECT 1 FROM salas WHERE codigo = ?", (usuario.sala,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=400, detail="Código de sala inválido.")
                codigo_sala = usuario.sala

            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha, cargo, sala) VALUES (?, ?, ?, ?, ?)",
                (usuario.nome, usuario.email, usuario.senha, usuario.cargo, codigo_sala)
            )

            conn.commit()

        return {
            "mensagem": "Usuário cadastrado com sucesso!",
            "codigo_sala": codigo_sala if usuario.cargo == "professor" else None
        }

    except sqlite3.IntegrityError as e:
        if "usuarios.email" in str(e):
            raise HTTPException(status_code=400, detail="Email já cadastrado.")
        elif "salas.email_professor" in str(e):
            raise HTTPException(status_code=400, detail="Este professor já criou uma sala.")
        else:
            raise HTTPException(status_code=500, detail="Erro ao cadastrar.")


@app.post("/login")
def login(usuario: LoginRequest):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT nome, senha, cargo, sala, email
            FROM usuarios
            WHERE email = ? OR nome = ?
            """,
            (usuario.identificador, usuario.identificador)
        )
        resultado = cursor.fetchone()

    if resultado and resultado[1] == usuario.senha:
        return {
            "mensagem": f"Login bem-sucedido. Bem-vindo, {resultado[0]}!",
            "nome": resultado[0],
            "cargo": resultado[2],
            "codigo_sala": resultado[3],
            "email": resultado[4]
        }

    raise HTTPException(status_code=401, detail="Email ou senha incorretos")
   



@app.get("/alunos/{codigo_sala}")
def listar_alunos_por_sala(codigo_sala: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT nome, email
            FROM usuarios
            WHERE sala = ? AND cargo = 'aluno'
            ORDER BY nome
        """, (codigo_sala,))
        
        alunos = cursor.fetchall()

    return [
        {"nome": nome, "email": email}
        for nome, email in alunos
    ]



@app.post("/publicar-tematica")
async def publicar_tematica(
    email_aluno: str = Form(...),
    codigo_sala: str = Form(...),
    titulo: str = Form(...),
    conteudo: str = Form(...)
):
    try:
        # Caminho fixo para imagem de tema proposto
        imagem_padrao = "images/tematica.jpg"
        tipo_publicacao = "tematica"

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Verifica se o aluno existe
            cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email_aluno,))
            aluno = cursor.fetchone()

            if aluno is None:
                raise HTTPException(status_code=400, detail="Aluno não encontrado com este email.")

            # Insere publicação
            cursor.execute(
                """
                INSERT INTO publicacoes (id_aluno, codigo_sala, tipo, titulo, conteudo, imagem)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (aluno[0], codigo_sala, tipo_publicacao, titulo, conteudo, imagem_padrao)
            )
            conn.commit()

        return {
            "mensagem": "Publicação temática enviada com sucesso!",
            "dados": {
                "email_aluno": email_aluno,
                "codigo_sala": codigo_sala,
                "tipo": tipo_publicacao,
                "titulo": titulo,
                "conteudo": conteudo,
                "imagem": imagem_padrao
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar produção temática: {str(e)}")


@app.post("/publicar-link")
async def publicar_link(
    email_aluno: str = Form(...),
    codigo_sala: str = Form(...),
    tipo: Literal["podcast", "tematica"] = Form(...),
    titulo: str = Form(...),
    conteudo: str = Form(...),
    imagem: str = Form(...)  # Aqui o "imagem" é o LINK
):
    try:
        if tipo not in ["podcast", "tematica"]:
            raise HTTPException(status_code=400, detail="Tipo inválido para essa rota.")

        caminho_arquivo = imagem.strip()  # salva o link diretamente

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email_aluno,))
            aluno = cursor.fetchone()
            if aluno is None:
                raise HTTPException(status_code=400, detail="Aluno não encontrado com este email.")

            cursor.execute(
                "INSERT INTO publicacoes (id_aluno, codigo_sala, tipo, titulo, conteudo, imagem) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (aluno[0], codigo_sala, tipo, titulo, conteudo, caminho_arquivo)
            )
            conn.commit()

        return {
            "mensagem": "Publicação enviada com sucesso!",
            "imagem": caminho_arquivo
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar publicação: {str(e)}")

# Rota: Criar publicação

@app.post("/publicar")
async def publicar(
    request: Request,
    email_aluno: str = Form(...),
    codigo_sala: str = Form(...),
    tipo: Literal["podcast", "fotografia", "tematica"] = Form(...),
    titulo: str = Form(...),
    conteudo: str = Form(...),
    imagem: UploadFile = File(None)

):
    try:
        os.makedirs("uploads", exist_ok=True)

        # Detectar se o campo imagem é UploadFile (foto) ou string (link)
        caminho_arquivo = None
        if tipo == "fotografia" and imagem is not None:

            nome_unico = f"{uuid.uuid4().hex}_{imagem.filename}"
            caminho_arquivo = nome_unico  # SALVA SÓ O NOME NO BANCO!
            with open(f"uploads/{nome_unico}", "wb") as buffer:
                shutil.copyfileobj(imagem.file, buffer)



        elif tipo in ["podcast", "tematica"] and isinstance(imagem, str):
            caminho_arquivo = imagem.strip()  # link do podcast/temática
        else:
            caminho_arquivo = None

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email_aluno,))
            aluno = cursor.fetchone()

            if aluno is None:
                raise HTTPException(status_code=400, detail="Aluno não encontrado com este email.")

            cursor.execute(
                "INSERT INTO publicacoes (id_aluno, codigo_sala, tipo, titulo, conteudo, imagem) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (aluno[0], codigo_sala, tipo, titulo, conteudo, caminho_arquivo)
            )
            conn.commit()
            url_imagem = f"http://localhost:8000/uploads/{caminho_arquivo}" if caminho_arquivo else None

        return {
              "mensagem": "Publicação enviada com sucesso!",
    "url_imagem": url_imagem,
    "dados": {
        "email_aluno": email_aluno,
        "codigo_sala": codigo_sala,
        "tipo": tipo,
        "titulo": titulo,
        "conteudo": conteudo,
        "imagem": caminho_arquivo
                
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar publicação: {str(e)}")

@app.get("/publicacao/{id}")
def get_publicacao_por_id(id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, u.nome, p.titulo, p.conteudo, p.tipo, p.imagem, p.data_criacao, u.email
            FROM publicacoes p
            JOIN usuarios u ON p.id_aluno = u.id
            WHERE p.id = ?
            """, (id,))

        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Publicação não encontrada")

        return {
            "id": row[0],
            "aluno": row[1],
            "titulo": row[2],
            "conteudo": row[3],
            "tipo": row[4],
            "imagem": row[5],
            "data_criacao": row[6],
            "email": row[7]  # ✅ agora vem do SELECT
}



# Rota: Listar publicações de uma sala
@app.get("/publicacoes/{codigo_sala}")
def listar_publicacoes(codigo_sala: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, u.nome, p.tipo, p.titulo, p.conteudo, p.imagem, p.data_criacao
            FROM publicacoes p
            JOIN usuarios u ON p.id_aluno = u.id
            WHERE p.codigo_sala = ?
            ORDER BY p.data_criacao DESC
        """, (codigo_sala,))
        dados = cursor.fetchall()

    return [
        {
            "id": id_,
            "aluno": nome,
            "tipo": tipo,
            "titulo": titulo,
            "conteudo": conteudo,
            "imagem": imagem,
            "data_criacao": data
        }
        for id_, nome, tipo, titulo, conteudo, imagem, data in dados
    ]





@app.patch("/publicacoes/{publicacao_id}/nota")
def atualizar_nota(publicacao_id: int = Path(..., description="ID da publicação"),
                   nota: float = Form(..., ge=0, le=10)):  # Exemplo: nota de 0 a 10
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM publicacoes WHERE id = ?", (publicacao_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Publicação não encontrada")

        cursor.execute("UPDATE publicacoes SET nota = ? WHERE id = ?", (nota, publicacao_id))
        conn.commit()

    return {"mensagem": "Nota atualizada com sucesso", "publicacao_id": publicacao_id, "nota": nota}


@app.get("/salas")
def listar_salas():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.codigo, u.nome, u.email
            FROM salas s
            JOIN usuarios u ON s.email_professor = u.email
        """)
        salas = cursor.fetchall()

    return [
        {
            "codigo": codigo,
            "professor_nome": nome,
            "professor_email": email
        }
        for codigo, nome, email in salas
    ]


def verificar_usuario_existe(email):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT nome FROM usuarios WHERE email = ?",
            (email,)
        )
        resultado = cursor.fetchone()

    if resultado:
        return resultado[0]  # Retorna o nome do usuário
    return None


#----------------------------------------CHAT----------------------------------------------



def save_message(sender_id: int, content: str, receiver_id: int = None):
    db = SessionLocal()
    msg = Message(sender_id=sender_id, receiver_id=receiver_id, content=content, timestamp=datetime.utcnow())
    db.add(msg)
    db.commit()
    db.close()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket, client_id)
    await manager.broadcast(f"Client #{client_id} joined the chat")
    await manager.send_user_list()

    try: 
        while True:
            data = await websocket.receive_text()

            # Mensagem privada
            if data.startswith("@"):
                try:
                    target_id, msg = data[1:].split(":", 1)
                    target_id = int(target_id.strip())
                    msg = msg.strip()
                    await manager.send_personal_message(f"[PRIVATE] From #{client_id}: {msg}", target_id)
                    await manager.send_personal_message(f"[PRIVATE] To #{target_id}: {msg}", client_id)
                    save_message(sender_id=client_id, receiver_id=target_id, content=msg)
                except Exception:
                    await manager.send_personal_message("❌ Invalid private message format. Use @<id>: <message>", client_id)
            else:
                await manager.send_personal_message(f"You wrote: {data}", client_id)
                await manager.broadcast(f"Client #{client_id} says: {data}")
                save_message(sender_id=client_id, content=data)
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        await manager.broadcast(f"Client #{client_id} has left the chat")
        await manager.send_user_list()
        
    

