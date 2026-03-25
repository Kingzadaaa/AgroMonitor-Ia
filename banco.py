from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Float, String, Date, Text, text
import pandas as pd

# ============= COLE SEU LINK DO SUPABASE AQUI =============
DB_URL = "postgresql+psycopg2://postgres.bcptmdptgqchzjhfngio:Projetoepamig2026@aws-1-us-east-2.pooler.supabase.com:6543/postgres"

# Criando o motor de conexão com a nuvem
engine = create_engine(DB_URL)
metadata = MetaData()

# Nova Tabela: Agora com a coluna 'dono' para separar os usuários
coletas = Table(
    "coletas_v8", metadata,
    Column("id", Integer, primary_key=True),
    Column("dono", String), 
    Column("data", Date),
    Column("hora", String),
    Column("planta", String),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("clima_externo_temp", Float),
    Column("clima_externo_umid", Float),
    Column("clima_desc", String),
    Column("sensor_local_umid", Float),
    Column("banda_azul", Integer),
    Column("banda_verde", Integer),
    Column("banda_vermelho", Integer),
    Column("banda_red_edge", Integer),
    Column("banda_nir", Integer),
    Column("banda_swir", Integer),
    Column("nota_geral", Integer),
    Column("observacao", Text),
    Column("audio_caminho", String),
    Column("ai_analise_json", Text)
)

# Cria a tabela no Supabase automaticamente se ela não existir
metadata.create_all(engine)

def salvar_no_banco(dados): 
    pd.DataFrame([dados]).to_sql("coletas_v8", engine, if_exists="append", index=False)

def ler_banco(usuario):
    query = f"SELECT * FROM coletas_v8 WHERE dono = '{usuario}'"
    return pd.read_sql(query, engine)

def excluir_registro(id_r, usuario):
    with engine.connect() as c: 
        c.execute(text("DELETE FROM coletas_v8 WHERE id = :id AND dono = :dono"), {"id": id_r, "dono": usuario})
        c.commit()

def salvar_bytes_audio(audio, planta, data):
    import os
    from datetime import datetime
    if audio:
        if not os.path.exists("audios"): os.makedirs("audios")
        nome = f"audios/{data.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}.wav"
        with open(nome, "wb") as f: f.write(audio)
        return nome
    return None

# ==========================================
# FUNÇÕES DE AUTENTICAÇÃO E LOGIN
# ==========================================

def ler_usuarios_supabase():
    """Lê os usuários do banco e formata para o Streamlit Authenticator."""
    config_dict = {'usernames': {}}
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT username, nome, senha_hash FROM usuarios"))
            for row in result:
                config_dict['usernames'][row[0]] = {
                    'name': row[1],
                    'password': row[2]
                }
    except Exception as e:
        print("Tabela de usuários ainda não existe ou vazia.")
    
    return config_dict

def registrar_novo_usuario(username, nome, senha_hash):
    """Cria a tabela se não existir e salva um novo usuário."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    username VARCHAR(50) PRIMARY KEY,
                    nome VARCHAR(100),
                    senha_hash VARCHAR(255)
                )
            """))
            conn.execute(text(
                "INSERT INTO usuarios (username, nome, senha_hash) VALUES (:user, :nome, :senha)"
            ), {"user": username, "nome": nome, "senha": senha_hash})
            conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao criar usuário: {e}")
        return False
