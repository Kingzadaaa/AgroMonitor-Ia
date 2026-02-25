from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Float, String, Date, Text, text
import pandas as pd

# ============= COLE SEU LINK DO SUPABASE AQUI =============
# Exemplo: "postgresql://postgres.xxx:suasenha@aws-0-sa-east-1..."
DB_URL = "postgresql+psycopg2://postgres.bcptmdptgqchzjhfngio:Projetoepamig2026@aws-1-us-east-2.pooler.supabase.com:6543/postgres"
# Criando o motor de conexão com a nuvem
engine = create_engine(DB_URL)
metadata = MetaData()

# Nova Tabela: Agora com a coluna 'dono' para separar os usuários
coletas = Table(
    "coletas_v8", metadata,
    Column("id", Integer, primary_key=True),
    Column("dono", String), # <-- O "crachá" do usuário
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
    # O filtro 'WHERE dono = ...' garante que um usuário não veja os dados do outro
    query = f"SELECT * FROM coletas_v8 WHERE dono = '{usuario}'"
    return pd.read_sql(query, engine)

def excluir_registro(id_r, usuario):
    with engine.connect() as c: 
        c.execute(text("DELETE FROM coletas_v8 WHERE id = :id AND dono = :dono"), {"id": id_r, "dono": usuario})
        c.commit()

def salvar_bytes_audio(audio, planta, data):
    # Por enquanto mantemos local, mas no Passo 3 vamos subir pro Supabase Storage
    import os
    from datetime import datetime
    if audio:
        if not os.path.exists("audios"): os.makedirs("audios")
        nome = f"audios/{data.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}.wav"
        with open(nome, "wb") as f: f.write(audio)
        return nome
    return None