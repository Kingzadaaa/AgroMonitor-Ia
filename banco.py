import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

# 1. Configuração da Conexão com Supabase
DB_URL = "postgresql+psycopg2://postgres.bcptmdptgqchzjhfngio:Projetoepamig2026@aws-1-us-east-2.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)

# ==========================================
# FUNÇÕES DE DADOS (COLETAS DO CAFÉ)
# ==========================================
def salvar_no_banco(dados):
    try:
        # 1. Garante que a tabela seja criada COM a coluna ID de auto-incremento
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS coletas_cafe (
                    id SERIAL PRIMARY KEY,
                    dono TEXT,
                    data TEXT,
                    hora TEXT,
                    planta TEXT,
                    latitude FLOAT,
                    longitude FLOAT,
                    clima_externo_temp FLOAT,
                    clima_externo_umid FLOAT,
                    clima_desc TEXT,
                    sensor_local_umid FLOAT,
                    nota_geral FLOAT,
                    ai_analise_json TEXT
                )
            """))
            
        # 2. Salva os dados anexando na tabela existente
        df = pd.DataFrame([dados])
        df.to_sql('coletas_cafe', engine, if_exists='append', index=False)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no banco: {e}")
        return False

def ler_banco(username):
    try:
        query = f"SELECT * FROM coletas_cafe WHERE dono = '{username}'"
        df = pd.read_sql(query, engine)
        return df
    except Exception:
        return pd.DataFrame()

def excluir_registro(id_registro, username):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM coletas_cafe WHERE id = :id AND dono = :dono"), 
                         {"id": id_registro, "dono": username})
        return True
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

def salvar_bytes_audio(audio_bytes):
    pass

# ==========================================
# FUNÇÕES DE USUÁRIOS (LOGIN E CADASTRO)
# ==========================================
def ler_usuarios_supabase():
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios_login (
                    username TEXT PRIMARY KEY,
                    name TEXT,
                    password TEXT
                )
            """))
            
            result = conn.execute(text("SELECT username, name, password FROM usuarios_login"))
            usuarios = {"usernames": {}}
            for row in result:
                usuarios["usernames"][row[0]] = {"name": row[1], "password": row[2]}
            return usuarios
    except Exception as e:
        st.error(f"Erro ao conectar com tabela de usuários: {e}")
        return {"usernames": {}}

def registrar_novo_usuario(username, name, password):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO usuarios_login (username, name, password) 
                VALUES (:u, :n, :p)
            """), {"u": username, "n": name, "p": password})
        return True
    except Exception as e:
        st.error(f"Erro ao salvar usuário no banco: {e}")
        return False
