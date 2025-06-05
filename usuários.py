import requests

URL = "http://localhost:8000"  # altere se estiver rodando em outra porta ou domínio
SALA = "DM2VEO"
SENHA = "123456"

alunos = [
    {"nome": "Maria Eduarda", "email": "mariaeduarda@gmail.com"},
    {"nome": "Lucas Oliveira", "email": "lucasoliveira@gmail.com"}
]

def cadastrar_alunos():
    for aluno in alunos:
        payload = {
            "nome": aluno["nome"],
            "email": aluno["email"],
            "senha": SENHA,
            "cargo": "aluno",
            "sala": SALA
        }

        response = requests.post(f"{URL}/cadastrar", json=payload)

        if response.status_code == 200:
            print(f"✅ {aluno['nome']} cadastrado com sucesso.")
        elif "Email já cadastrado" in response.text:
            print(f"⚠️ {aluno['nome']} já está cadastrado.")
        else:
            print(f"❌ Erro ao cadastrar {aluno['nome']}: {response.text}")
