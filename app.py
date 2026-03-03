import streamlit as st
import streamlit_authenticator as stauth
from datetime import date, datetime
import json
import os
import pandas as pd
import time
from PIL import Image
import io
import numpy as np

# --- Importando seus módulos personalizados ---
from banco import salvar_no_banco, ler_banco, excluir_registro, salvar_bytes_audio, ler_usuarios_supabase, registrar_novo_usuario
from hardware import get_weather_data, listar_portas_com, ler_sensor_esp, ler_sensor_wifi
from ia_core import analisar_imagem_gemini
from streamlit_mic_recorder import mic_recorder

# Configuração da página
st.set_page_config(page_title="AgroMonitor IA", layout="wide")

# ==========================================
# 1. SISTEMA DE AUTENTICAÇÃO
# ==========================================
config_usuarios = ler_usuarios_supabase()

if not config_usuarios["usernames"]:
    registrar_novo_usuario("marco", "Marco Antonio", "$2b$12$49wvxABeVD6FyIsDuZGCK.h.axhgxTdJMqLZaW/ZJGJFzFe.1L9gy")
    config_usuarios = ler_usuarios_supabase()

authenticator = stauth.Authenticate(
    config_usuarios,
    "agromonitor_cookie",
    "agromonitor_key",
    cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login(location='main')

# ==========================================
# 2. ÁREA RESTRITA
# ==========================================
if authentication_status:
    st.sidebar.title(f"Olá, {name}!")
    authenticator.logout("Sair do Sistema", "sidebar")
    
    st.sidebar.divider()
    pagina = st.sidebar.radio("Navegação", [
        "Dashboard Analítico", 
        "Nova Coleta de Dados", 
        "Histórico e Mapas", 
        "Manual Prático"
    ])
    st.sidebar.divider()
    
    weather_key = st.sidebar.text_input("OpenWeather Key", type="password")
    google_key = st.sidebar.text_input("Google Gemini Key", type="password")
    
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
        
    if "amostras_dict" not in st.session_state:
        st.session_state.amostras_dict = {
            "Amostra 1": {
                "nome": "", "umid": 0.0, "saude": 10.0,
                "notas_bandas": {"blue": 10, "green": 10, "red": 10, "rededge": 10, "nir": 10, "pan": 10}
            }
        }

    # ------------------------------------------
    # PÁGINA: DASHBOARD
    # ------------------------------------------
    if pagina == "Dashboard Analítico":
        st.title(f"📊 Painel de Controle: {name}")
        df_dash = ler_banco(username) 
        
        if not df_dash.empty:
            # Padronização de colunas para evitar KeyError
            df_dash.columns = [c.lower() for c in df_dash.columns]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Amostras", len(df_dash))
            
            # Verificações de segurança antes de calcular métricas
            if 'nota_geral' in df_dash.columns:
                c2.metric("Saúde Média", f"{round(df_dash['nota_geral'].mean(), 1)} / 10")
            if 'sensor_local_umid' in df_dash.columns:
                c3.metric("Umidade Solo Média", f"{round(df_dash['sensor_local_umid'].mean(), 1)} %")
            if 'clima_externo_temp' in df_dash.columns:
                c4.metric("Temp. Média Ar", f"{round(df_dash['clima_externo_temp'].mean(), 1)} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            if 'latitude' in df_dash.columns and 'longitude' in df_dash.columns:
                st.map(df_dash[['latitude', 'longitude']], zoom=14)
        else:
            st.info("Nenhuma coleta registrada.")

    # ------------------------------------------
    # PÁGINA: NOVA COLETA
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem")
        
        with st.container(border=True):
            st.markdown("#### 📍 Localização")
            c1, c2, c3 = st.columns(3)
            with c1: dt = st.date_input("Data", date.today())
            with c2: lat = st.number_input("Lat", value=-20.91, format="%.6f")
            with c3: lon = st.number_input("Lon", value=-46.98, format="%.6f")

        col_cl, col_so = st.columns(2)
        with col_cl:
            with st.container(border=True):
                if st.button("Buscar Clima"):
                    d, s = get_weather_data(lat, lon, weather_key)
                    if d: st.session_state.clima_atual = {"temp": d['main']['temp'], "umid": d['main']['humidity'], "desc": d['weather'][0]['description']}
                st.write(f"Temp: {st.session_state.clima_atual['temp']}°C")

        with col_so:
            with st.container(border=True):
                if st.button("Sincronizar Sensor Wi-Fi"):
                    d_wifi, msg = ler_sensor_wifi(username)
                    if d_wifi:
                        st.session_state.sensor_iot = d_wifi
                        st.success("Sincronizado!")
                st.write(f"Solo: {st.session_state.sensor_iot.get('umid', 0)} %")

        st.divider()
        amostra_atual = st.selectbox("Amostra Ativa:", list(st.session_state.amostras_dict.keys()))
        
        with st.container(border=True):
            dados = st.session_state.amostras_dict[amostra_atual]
            dados["nome"] = st.text_input("ID Planta", value=dados["nome"])
            dados["umid"] = st.number_input("Umidade Solo %", value=float(dados["umid"]))
            dados["saude"] = st.slider("Nota Saúde", 0.0, 10.0, float(dados["saude"]))

        if st.button("💾 GRAVAR NO BANCO", type="primary", use_container_width=True):
            for k, v in st.session_state.amostras_dict.items():
                if v["nome"].strip():
                    payload = {
                        "dono": username, "data": dt, "hora": datetime.now().strftime("%H:%M"),
                        "planta": v["nome"], "latitude": lat, "longitude": lon,
                        "clima_externo_temp": st.session_state.clima_atual['temp'],
                        "clima_externo_umid": st.session_state.clima_atual['umid'],
                        "clima_desc": st.session_state.clima_atual['desc'],
                        "sensor_local_umid": v["umid"], "nota_geral": v["saude"],
                        "ai_analise_json": json.dumps({"notas": v["notas_bandas"]})
                    }
                    salvar_no_banco(payload)
            st.success("Dados salvos com sucesso!")

    # ------------------------------------------
    # PÁGINA: HISTÓRICO (Onde ocorria o erro)
    # ------------------------------------------
    elif pagina == "Histórico e Mapas":
        st.title("📂 Histórico")
        df = ler_banco(username)
        
        if not df.empty:
            # SOLUÇÃO PARA O KEYERROR: Forçar todas as colunas para minúsculo
            df.columns = [c.lower() for c in df.columns]
            
            st.dataframe(df, use_container_width=True)
            
            st.divider()
            st.subheader("🗑️ Gerenciamento de Dados")
            c1, c2 = st.columns(2)
            
            with c1:
                id_del = st.number_input("Excluir por ID", min_value=0)
                if st.button("🗑️ Apagar Registro"):
                    excluir_registro(id_del, username)
                    st.rerun()
            
            with c2:
                confirmar = st.checkbox("Desejo apagar TODO o histórico")
                if confirmar:
                    if st.button("🚨 EXCLUIR TUDO", type="primary"):
                        # Verifica se a coluna 'id' existe após a conversão
                        if 'id' in df.columns:
                            for id_at in df['id'].tolist():
                                excluir_registro(id_at, username)
                            st.success("Histórico limpo!")
                            st.rerun()
                        else:
                            st.error("Erro: Coluna 'id' não encontrada no banco.")
        else:
            st.info("Nenhum dado encontrado.")

    elif pagina == "Manual Prático":
        st.title("📖 Manual")
        st.info("Instruções de hardware e coleta de dados.")

# ==========================================
# 3. TRATAMENTO DE ACESSO
# ==========================================
elif authentication_status == False:
    st.error("Usuário/Senha incorretos.")
elif authentication_status == None:
    st.warning("Por favor, faça login.")
    with st.expander("Novo por aqui? Cadastre-se"):
        with st.form("cad"):
            un = st.text_input("User").lower()
            pw = st.text_input("Pass", type="password")
            if st.form_submit_button("Criar Conta"):
                h_pw = stauth.Hasher([pw]).generate()[0]
                if registrar_novo_usuario(un, un, h_pw):
                    st.success("Cadastrado! Faça o login acima.")
