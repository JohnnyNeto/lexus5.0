from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
import json
import sqlite3
import urllib.parse
from datetime import datetime


app = FastAPI()

DB_FILE = "usuarios.db"

with sqlite3.connect("usuarios.db") as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE mensagens ADD COLUMN entregue INTEGER DEFAULT 0;")
        conn.commit()
        print("Coluna 'entregue' adicionada com sucesso.")
    except sqlite3.OperationalError as e:
        print(f"Erro ao adicionar coluna: {e}")



html = """
<!DOCTYPE html>
<html>
    <head>
        <title>WebSocket Chat with Email</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-3">
            <div id="login-section" class="card">
                <div class="card-header">
                    <h3>Enter Chat</h3>
                </div>
                <div class="card-body">
                    <form onsubmit="connectWebSocket(event)">
                        <div class="mb-3">
                            <label for="email" class="form-label">Your Email</label>
                            <input type="email" class="form-control" id="email" required>
                        </div>
                        <button type="submit" class="btn btn-primary">Join Chat</button>
                    </form>
                </div>
            </div>

            <div id="chat-section" style="display: none;">
                <h2 class="mt-3">Logged in as: <span id="user-email"></span></h2>
                
                <div class="card mt-3">
                    <div class="card-header">Online Users</div>
                    <div class="card-body">
                        <ul id="online-users" class="list-group"></ul>
                    </div>
                </div>

                <div class="card mt-3">
                    <div class="card-header">Public Message</div>
                    <div class="card-body">
                        <form onsubmit="sendPublicMessage(event)">
                            <input type="text" class="form-control" id="publicMessage" placeholder="Type your message">
                            <button class="btn btn-primary mt-2">Send</button>
                        </form>
                    </div>
                </div>

                <div class="card mt-3">
                    <div class="card-header">Private Message</div>
                    <div class="card-body">
                        <form onsubmit="sendPrivateMessage(event)">
                            <select class="form-select mb-2" id="recipient-email" required>
                                <option value="">Select recipient</option>
                            </select>
                            <input type="text" class="form-control" id="privateMessage" placeholder="Type your private message">
                            <button class="btn btn-success mt-2">Send Private</button>
                        </form>
                    </div>
                </div>

                <ul id="messages" class="list-group mt-3"></ul>
            </div>
        </div>

        <script>
            let ws;
            let currentUserEmail = '';
            let onlineUsers = {};

            async function carregarContatos(email) {
                try {
                    const response = await fetch(`/contatos/${encodeURIComponent(email)}`);
                    if (!response.ok) {
                        console.error("Erro ao buscar contatos");
                        return;
                    }
                    const data = await response.json();
                    const recipientSelect = document.getElementById('recipient-email');

                    // Limpa opções atuais, exceto a primeira
                    recipientSelect.innerHTML = '<option value="">Select recipient</option>';

                    data.contatos.forEach(contato => {
                        if(contato !== email) { // evitar adicionar o próprio email
                            const option = document.createElement('option');
                            option.value = contato;
                            option.textContent = contato;
                            recipientSelect.appendChild(option);
                        }
                    });
                } catch (error) {
                    console.error("Erro ao carregar contatos:", error);
                }
            }

            function connectWebSocket(event) {
                event.preventDefault();
                currentUserEmail = document.getElementById('email').value;

                ws = new WebSocket(`ws://localhost:8000/ws/${encodeURIComponent(currentUserEmail)}`);

                ws.onopen = () => {
                    document.getElementById('login-section').style.display = 'none';
                    document.getElementById('chat-section').style.display = 'block';
                    document.getElementById('user-email').textContent = currentUserEmail;

                    carregarContatos(currentUserEmail); // chama a nova função para carregar contatos
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);

                    if (data.type === 'user_list') {
                        updateOnlineUsers(data.users);
                    } else if (data.type === 'message') {
                        addMessage(data.content, data.is_private);
                    }
                };
            }

            function updateOnlineUsers(users) {
                const usersList = document.getElementById('online-users');

                // Clear existing online users list
                usersList.innerHTML = '';

                // Add current users
                users.forEach(email => {
                    if (email !== currentUserEmail) {
                        // Add to online users list
                        const userItem = document.createElement('li');
                        userItem.className = 'list-group-item';
                        userItem.textContent = email;
                        usersList.appendChild(userItem);
                    }
                });
            }

            function addMessage(content, isPrivate) {
                const messages = document.getElementById('messages');
                const message = document.createElement('li');
                message.className = `list-group-item ${isPrivate ? 'list-group-item-primary' : ''}`;
                message.textContent = content;
                messages.appendChild(message);
                messages.scrollTop = messages.scrollHeight;
            }

            function sendPublicMessage(event) {
                event.preventDefault();
                const input = document.getElementById('publicMessage');
                ws.send(JSON.stringify({
                    type: 'public_message',
                    content: input.value
                }));
                input.value = '';
            }

            function sendPrivateMessage(event) {
                event.preventDefault();
                const recipient = document.getElementById('recipient-email').value;
                const input = document.getElementById('privateMessage');

                if (!recipient) {
                    alert('Selecione um destinatário para enviar a mensagem privada.');
                    return;
                }

                ws.send(JSON.stringify({
                    type: 'private_message',
                    recipient: recipient,
                    content: input.value
                }));

                input.value = '';
            }

            async function carregarHistorico(contatoEmail) {
                const messagesList = document.getElementById('messages');
                messagesList.innerHTML = '';

                if (!contatoEmail) {
                    return;
                }

                try {
                    const response = await fetch(`/mensagens/historico/${encodeURIComponent(currentUserEmail)}/${encodeURIComponent(contatoEmail)}`);
                    if (!response.ok) {
                        messagesList.innerHTML = '<li class="list-group-item text-muted">Nenhum histórico encontrado.</li>';
                        return;
                    }

                    const mensagens = await response.json();

                    mensagens.forEach(msg => {
                        const li = document.createElement('li');
                        const isPrivate = msg.destinatario !== null;
                        li.className = 'list-group-item ' + (isPrivate ? 'list-group-item-primary' : '');
                        li.textContent = `[${msg.timestamp}] ${msg.remetente} → ${msg.destinatario || "Todos"}: ${msg.mensagem}`;
                        messagesList.appendChild(li);
                    });

                    messagesList.scrollTop = messagesList.scrollHeight;

                } catch (error) {
                    console.error('Erro ao carregar histórico:', error);
                }
            }

            document.getElementById('recipient-email').addEventListener('change', (event) => {
                const contato = event.target.value;
                carregarHistorico(contato);
            });
        </script>
    </body>
</html>
"""




class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, email: str):
        await websocket.accept()
        self.active_connections[email] = websocket
        await self.notify_user_list()

    async def disconnect(self, email: str):
        if email in self.active_connections:
            del self.active_connections[email]
            await self.notify_user_list()

    async def send_personal_message(self, message: str, email: str):
        if email in self.active_connections:
            try:
                await self.active_connections[email].send_text(message)
            except:
                await self.disconnect(email)

    async def broadcast(self, message: str, exclude: str = None):
        for email, connection in list(self.active_connections.items()):  # Usamos list() para evitar RuntimeError
            if email != exclude:
                try:
                    await connection.send_text(message)
                except:
                    await self.disconnect(email)

    async def notify_user_list(self):
        user_list = list(self.active_connections.keys())
        message = {
            "type": "user_list",
            "users": user_list
        }
        for connection in list(self.active_connections.values()):  # Usamos list() para evitar RuntimeError
            try:
                await connection.send_json(message)
            except:
                # Remove conexões inválidas
                for email, conn in list(self.active_connections.items()):
                    if conn == connection:
                        del self.active_connections[email]

manager = ConnectionManager()

@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws/{email}")
async def websocket_endpoint(websocket: WebSocket, email: str):
    email = urllib.parse.unquote(email)
    await manager.connect(websocket, email)

    # 🔄 Enviar mensagens pendentes
    entregar_mensagens_pendentes(email)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)

                if message['type'] == 'public_message':
                    salvar_mensagem(remetente=email, destinatario=None, mensagem=message['content'])

                    await manager.broadcast(
                        json.dumps({
                            "type": "message",
                            "content": f"Public message from {email}: {message['content']}",
                            "is_private": False
                        }),
                        exclude=email
                    )

                elif message['type'] == 'private_message':
                    recipient = message['recipient']
                    content = message['content']

                    salvar_mensagem(remetente=email, destinatario=recipient, mensagem=content)

                    # 🔍 Se destinatário estiver online, envia
                    if recipient in manager.active_connections:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "message",
                                "content": f"Private from {email}: {content}",
                                "is_private": True
                            }),
                            recipient
                        )
                        # Marca como entregue
                        marcar_como_entregue(email, recipient, content)

                    # ✅ Confirmação para remetente
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "message",
                            "content": f"Private to {recipient}: {content}",
                            "is_private": True
                        }),
                        email
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({
                        "type": "error",
                        "content": "Invalid message format"
                    }),
                    email
                )

    except WebSocketDisconnect:
        await manager.disconnect(email)
        await manager.broadcast(
            json.dumps({
                "type": "message",
                "content": f"User {email} has left the chat",
                "is_private": False
            })
        )



def salvar_mensagem(remetente: str, destinatario: str | None, mensagem: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mensagens (remetente, destinatario, mensagem, entregue)
            VALUES (?, ?, ?, 0)
        """, (remetente, destinatario, mensagem))
        conn.commit()


@app.get("/mensagens/historico/{email}/{contato}")
def obter_historico_filtrado(email: str, contato: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT remetente, destinatario, mensagem, timestamp
            FROM mensagens
            WHERE (remetente = ? AND destinatario = ?)
               OR (remetente = ? AND destinatario = ?)
            ORDER BY timestamp ASC
        """, (email, contato, contato, email))
        mensagens = cursor.fetchall()

    if not mensagens:
        raise HTTPException(status_code=404, detail="Nenhuma mensagem encontrada entre esses usuários")

    historico = []
    for remetente, destinatario, mensagem, timestamp in mensagens:
        historico.append({
            "remetente": remetente,
            "destinatario": destinatario,
            "mensagem": mensagem,
            "timestamp": timestamp
        })
    return historico


@app.get("/contatos/{email}")
def obter_contatos(email: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT
                CASE
                    WHEN remetente = ? THEN destinatario
                    ELSE remetente
                END AS contato
            FROM mensagens
            WHERE remetente = ? OR destinatario = ?
            AND contato IS NOT NULL
        """, (email, email, email))
        
        contatos = [row[0] for row in cursor.fetchall() if row[0] is not None]

    return {"contatos": contatos}



def entregar_mensagens_pendentes(destinatario: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, remetente, mensagem
            FROM mensagens
            WHERE destinatario = ? AND entregue = 0
            ORDER BY timestamp ASC
        """, (destinatario,))
        pendentes = cursor.fetchall()

        for msg_id, remetente, mensagem in pendentes:
            try:
                # Enviar para destinatário se estiver online
                if destinatario in manager.active_connections:
                    import asyncio
                    asyncio.create_task(
                        manager.send_personal_message(
                            json.dumps({
                                "type": "message",
                                "content": f"Private from {remetente}: {mensagem}",
                                "is_private": True
                            }),
                            destinatario
                        )
                    )

                    cursor.execute("""
                        UPDATE mensagens SET entregue = 1 WHERE id = ?
                    """, (msg_id,))
            except Exception as e:
                print(f"Erro ao entregar mensagem pendente: {e}")

        conn.commit()


def marcar_como_entregue(remetente: str, destinatario: str, mensagem: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM mensagens
            WHERE remetente = ? AND destinatario = ? AND mensagem = ? AND entregue = 0
            ORDER BY timestamp ASC
            LIMIT 1
        """, (remetente, destinatario, mensagem))
        result = cursor.fetchone()

        if result:
            msg_id = result[0]
            cursor.execute("""
                UPDATE mensagens SET entregue = 1 WHERE id = ?
            """, (msg_id,))
            conn.commit()


# --- Inicialização da tabela, caso não exista ---
def criar_tabela_mensagens():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remetente TEXT NOT NULL,
                destinatario TEXT,
                mensagem TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                entregue BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()


criar_tabela_mensagens()