import streamlit as st
import streamlit_authenticator as stauth
from datetime import date, datetime
import json
import os
import pandas as pd 
import time
from PIL import Image # Nova importação para lidar com os arquivos .tif
import io

# --- Importando seus módulos personalizados ---
from banco import salvar_no_banco, ler_banco, excluir_registro, salvar_bytes_audio, ler_usuarios_supabase, registrar_novo_usuario
from hardware import get_weather_data, listar_portas_com, ler_sensor_esp, ler_sensor_wifi
from ia_core import analisar_imagem_gemini, preparar_imagem_para_ia
from exportacao import gerar_kml_google_earth, gerar_laudo_pdf
from streamlit_mic_recorder import mic_recorder

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

st.write("#") 
name, authentication_status, username = authenticator.login(location='main')

# ==========================================
# 2. ÁREA RESTRITA
# ==========================================
if authentication_status:
    st.sidebar.title(f"Olá, {name}!")
    authenticator.logout("Sair do Sistema", "sidebar")
    
    st.sidebar.divider()
    pagina = st.sidebar.radio("Navegação", ["Dashboard Analítico", "Nova Coleta de Dados", "Histórico e Mapas", "Ajuda"])
    st.sidebar.divider()
    
    weather_key = st.sidebar.text_input("OpenWeather Key", type="password")
    google_key = st.sidebar.text_input("Google Gemini Key", type="password")
    
    # --- Variáveis de Memória (Session State) ---
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
    # Novo: Controle de quantidade de amostras na tela (começa com 4)
    if "num_amostras" not in st.session_state:
        st.session_state.num_amostras = 4

    # ------------------------------------------
    # PÁGINA: DASHBOARD
    # ------------------------------------------
    if pagina == "Dashboard Analítico":
        st.title(f"📊 Painel de Controle: {name}")
        df_dash = ler_banco(username) 
        
        if not df_dash.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Amostras", len(df_dash))
            c2.metric("Saúde Média", f"{round(df_dash['nota_geral'].mean(), 1)} / 10")
            c3.metric("Umidade Solo Média", f"{round(df_dash['sensor_local_umid'].mean(), 1)} %")
            c4.metric("Temp. Média Ar", f"{round(df_dash['clima_externo_temp'].mean(), 1)} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            st.map(df_dash[['latitude', 'longitude']], zoom=14, color="#00ff00")
        else:
            st.info("Você ainda não possui coletas registradas no Supabase.")

    # ------------------------------------------
    # PÁGINA: NOVA COLETA (AGORA DINÂMICA)
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem Múltipla")
        
        # Dados Gerais do Lote
        with st.container(border=True):
            st.markdown("#### 📍 Dados Gerais do Lote")
            c1, c2, c3 = st.columns(3)
            with c1:
                dt = st.date_input("Data da Coleta", date.today())
            with c2:
                lat = st.number_input("Latitude Base", value=-20.91, format="%.6f")
            with c3:
                lon = st.number_input("Longitude Base", value=-46.98, format="%.6f")

        # Clima e Nuvem IoT
        col_cl, col_so = st.columns(2)
        with col_cl:
            with st.container(border=True):
                st.subheader("🌦️ Clima Atual")
                if st.button("Buscar Clima", use_container_width=True):
                    d, s = get_weather_data(lat, lon, weather_key)
                    if d: st.session_state.clima_atual = {"temp": d['main']['temp'], "umid": d['main']['humidity'], "desc": d['weather'][0]['description'].title()}
                st.write(f"Temperatura: {st.session_state.clima_atual['temp']}°C | Umidade Ar: {st.session_state.clima_atual['umid']}%")

        with col_so:
            with st.container(border=True):
                st.subheader("☁️ Sensor Wi-Fi Global")
                if st.button("Puxar Dado do Servidor", type="primary", use_container_width=True):
                    d_wifi, msg = ler_sensor_wifi(username)
                    if d_wifi:
                        st.session_state.sensor_iot = d_wifi
                        st.success("Sincronizado!")
                    else:
                        st.error(msg)
                st.write(f"Última leitura global: {st.session_state.sensor_iot.get('umid', 0)} %")

        st.divider()

        # --- SISTEMA DINÂMICO DE AMOSTRAS ---
        st.markdown("### 🌿 Registro de Amostras")
        
        col_add, col_rem, _ = st.columns([1, 1, 2])
        with col_add:
            if st.button("➕ Incluir Amostra", use_container_width=True):
                st.session_state.num_amostras += 1
        with col_rem:
            if st.button("➖ Excluir Amostra", use_container_width=True):
                if st.session_state.num_amostras > 1:
                    st.session_state.num_amostras -= 1
                else:
                    st.warning("Você precisa ter pelo menos 1 amostra.")

        # Lista para guardar os dados preenchidos
        dados_amostras = []
        
        # Gera os formulários com base na quantidade escolhida
        for i in range(st.session_state.num_amostras):
            with st.expander(f"Amostra {i+1}", expanded=True):
                c_nome, c_umid = st.columns([2, 1])
                with c_nome:
                    nome = st.text_input("Identificação do Pé/Ponto", placeholder=f"Ex: Quadra 4 - Pé {i+1}", key=f"nome_{i}")
                with c_umid:
                    # Puxa o valor do sensor global por padrão, mas permite você alterar
                    umid = st.number_input("Umidade do Solo (%)", value=float(st.session_state.sensor_iot.get("umid", 0)), key=f"umid_{i}")
                
                # Guarda os dados dessa amostra num dicionário temporário
                dados_amostras.append({"planta": nome, "umid": umid})

        st.divider()

        # --- UPLOAD E IA (AGORA COM .TIF) ---
        with st.container(border=True):
            st.subheader("🧠 Análise Geral por IA (Lote)")
            # Adicionado o .tif e .tiff
            fotos = st.file_uploader("Fotos do Lote/Folhas", type=["jpg", "png", "tif", "tiff"], accept_multiple_files=True)
            
            if fotos and st.button("Analisar com Gemini"):
                with st.spinner("Processando imagens..."):
                    fotos_prontas = []
                    for foto in fotos:
                        # Se for TIF, converte para JPG na memória antes de mandar pra IA
                        if foto.name.lower().endswith(('.tif', '.tiff')):
                            img = Image.open(foto)
                            img = img.convert("
