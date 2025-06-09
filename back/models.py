from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

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
            const onlineUsers = {};

            function connectWebSocket(event) {
                event.preventDefault();
                currentUserEmail = document.getElementById('email').value;
                
                ws = new WebSocket(`ws://localhost:8000/ws/${encodeURIComponent(currentUserEmail)}`);
                
                ws.onopen = () => {
                    document.getElementById('login-section').style.display = 'none';
                    document.getElementById('chat-section').style.display = 'block';
                    document.getElementById('user-email').textContent = currentUserEmail;
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
                onlineUsers = users;
                const usersList = document.getElementById('online-users');
                const recipientSelect = document.getElementById('recipient-email');
                
                // Clear existing options except the first one
                usersList.innerHTML = '';
                recipientSelect.innerHTML = '<option value="">Select recipient</option>';
                
                // Add current users
                users.forEach(email => {
                    if (email !== currentUserEmail) {
                        // Add to online users list
                        const userItem = document.createElement('li');
                        userItem.className = 'list-group-item';
                        userItem.textContent = email;
                        usersList.appendChild(userItem);
                        
                        // Add to recipient dropdown
                        const option = document.createElement('option');
                        option.value = email;
                        option.textContent = email;
                        recipientSelect.appendChild(option);
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
                
                ws.send(JSON.stringify({
                    type: 'private_message',
                    recipient: recipient,
                    content: input.value
                }));
                
                input.value = '';
            }
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
            await self.active_connections[email].send_text(message)

    async def broadcast(self, message: str, exclude: str = None):
        for email, connection in self.active_connections.items():
            if email != exclude:
                await connection.send_text(message)

    async def notify_user_list(self):
        user_list = list(self.active_connections.keys())
        message = {
            "type": "user_list",
            "users": user_list
        }
        for connection in self.active_connections.values():
            await connection.send_json(message)

manager = ConnectionManager()

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/ws/{email}")
async def websocket_endpoint(websocket: WebSocket, email: str):
    await manager.connect(websocket, email)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)  # Usando json.loads em vez de JSON.parse
                
                if message['type'] == 'public_message':
                    await manager.broadcast(
                        json.dumps({
                            "type": "message",
                            "content": f"Public message from {email}: {message['content']}",
                            "is_private": False
                        }),
                        exclude=email
                    )
                elif message['type'] == 'private_message':
                    # Send to recipient
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "message",
                            "content": f"Private from {email}: {message['content']}",
                            "is_private": True
                        }),
                        message['recipient']
                    )
                    # Send confirmation to sender
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "message",
                            "content": f"Private to {message['recipient']}: {message['content']}",
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
    await manager.connect(websocket, email)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.parse(data)
            
            if message['type'] == 'public_message':
                await manager.broadcast(
                    json.stringify({
                        "type": "message",
                        "content": f"Public message from {email}: {message['content']}",
                        "is_private": False
                    }),
                    exclude=email
                )
            elif message['type'] == 'private_message':
                # Send to recipient
                await manager.send_personal_message(
                    json.stringify({
                        "type": "message",
                        "content": f"Private from {email}: {message['content']}",
                        "is_private": True
                    }),
                    message['recipient']
                )
                # Send confirmation to sender
                await manager.send_personal_message(
                    json.stringify({
                        "type": "message",
                        "content": f"Private to {message['recipient']}: {message['content']}",
                        "is_private": True
                    }),
                    email
                )
                
    except WebSocketDisconnect:
        await manager.disconnect(email)
        await manager.broadcast(
            json.stringify({
                "type": "message",
                "content": f"User {email} has left the chat",
                "is_private": False
            })
        )