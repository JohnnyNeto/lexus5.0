import subprocess

if __name__ == "__main__":
    chat = subprocess.Popen(["uvicorn", "models:app", "--host", "127.0.0.1", "--port", "8080", "--reload"])
    sistema = subprocess.Popen(["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"])

    print("Ambos os servidores estão rodando.")
    chat.wait()
    sistema.wait()
