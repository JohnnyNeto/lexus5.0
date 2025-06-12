import sqlite3

conexao = sqlite3.connect("usuarios.db")
cursor = conexao.cursor()

# Apagar publicação com id X (mude conforme necessário)
id_publicacao = 53
cursor.execute("DELETE FROM publicacoes WHERE id = ?", (id_publicacao,))

conexao.commit()
conexao.close()
print("Publicação apagada com sucesso.")
