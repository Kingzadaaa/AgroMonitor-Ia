import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

# 1. Configuração da Conexão com Supabase (Link corrigido para nuvem)
DB_URL = "postgresql+psycopg2://postgres.bcptmdptgqchzjhfngio:Projetoepamig2026@aws-1-us-east-2.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)

# ==========================================
# FUNÇÕES DE DADOS (COLETAS DO CAFÉ)
# ==========================================
def salvar_no_banco(dados):
    try:
        df = pd.DataFrame([dados])
        # Salva os dados na tabela 'coletas_cafe' (cria automaticamente se não existir)
        df.to_sql('coletas_cafe', engine, if_exists='append', index=False)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no banco: {e}")
        return False

def ler_banco(username):
    try:
        # Lê apenas os dados do usuário que está logado no momento
        query = f"SELECT * FROM coletas_cafe WHERE dono = '{username}'"
        df = pd.read_sql(query, engine)
        return df
    except Exception:
        # Retorna um DataFrame vazio se a tabela ainda não existir
        return pd.DataFrame()

def excluir_registro(id_registro, username):
    try:
        with engine.begin() as conn:
            # Exclui pelo ID e garante que o dono é quem está pedindo a exclusão
            conn.execute(text("DELETE FROM coletas_cafe WHERE id = :id AND dono = :dono"), 
                         {"id": id_registro, "dono": username})
        return True
    except Exception as e:
        st.error(f"Erro ao excluir: {e}")
        return False

def salvar_bytes_audio(audio_bytes):
    # Função mantida vazia apenas para não quebrar a importação do app.py
    pass

# ==========================================
# FUNÇÕES DE USUÁRIOS (LOGIN E CADASTRO)
# ==========================================
def ler_usuarios_supabase():
    try:
        with engine.begin() as conn:
            # 1. Cria a tabela de usuários automaticamente se ela não existir
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios_login (
                    username TEXT PRIMARY KEY,
                    name TEXT,
                    password TEXT
                )
            """))
            
            # 2. Busca todos os usuários cadastrados no Supabase
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
