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
                            img = img.convert("RGB")
                            byte_io = io.BytesIO()
                            img.save(byte_io, format="JPEG")
                            # Simula um arquivo JPG para a sua função de IA
                            byte_io.name = "imagem_convertida.jpg"
                            byte_io.seek(0)
                            fotos_prontas.append(byte_io)
                        else:
                            fotos_prontas.append(foto)
                            
                    # Manda as fotos (convertidas ou não) para o Gemini
                    st.session_state.ai_results = analisar_imagem_gemini(fotos_prontas, google_key)
                st.success("Análise Finalizada!")
            
            if st.session_state.ai_results:
                st.markdown("#### 📋 Diagnóstico da IA:")
                if isinstance(st.session_state.ai_results, dict):
                    for chave, valor in st.session_state.ai_results.items():
                        st.write(f"**{chave.title()}:** {valor}")
                else:
                    st.write(st.session_state.ai_results)

        st.divider()
        
        # --- SALVAR TODAS AS AMOSTRAS DE UMA VEZ ---
        if st.button("💾 FINALIZAR E SALVAR TODAS AS AMOSTRAS", use_container_width=True, type="primary"):
            amostras_salvas = 0
            for amostra in dados_amostras:
                if amostra["planta"].strip() != "": # Só salva se você deu um nome para a amostra
                    dados_para_salvar = {
                        "dono": username, 
                        "data": dt,
                        "hora": datetime.now().strftime("%H:%M"),
                        "planta": amostra["planta"],
                        "latitude": lat,
                        "longitude": lon,
                        "clima_externo_temp": st.session_state.clima_atual['temp'],
                        "clima_externo_umid": st.session_state.clima_atual['umid'],
                        "clima_desc": st.session_state.clima_atual['desc'],
                        "sensor_local_umid": amostra["umid"], # Pega a umidade específica daquela amostra
                        "nota_geral": 10,
                        "ai_analise_json": json.dumps(st.session_state.ai_results) if st.session_state.ai_results else ""
                    }
                    salvar_no_banco(dados_para_salvar)
                    amostras_salvas += 1
            
            if amostras_salvas > 0:
                st.success(f"Sucesso! {amostras_salvas} amostra(s) registrada(s) no Supabase!")
                st.session_state.ai_results = None 
            else:
                st.warning("Preencha a 'Identificação' de pelo menos uma amostra para salvar.")

    # ------------------------------------------
    # PÁGINA: HISTÓRICO
    # ------------------------------------------
    elif pagina == "Histórico e Mapas":
        st.title("📂 Meu Histórico")
        df = ler_banco(username) 
        
        if not df.empty:
            with st.expander("🔍 Filtros de Busca", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    lista_plantas = df['planta'].unique().tolist()
                    lista_plantas.insert(0, "Todas as Plantas")
                    filtro_planta = st.selectbox("Filtrar por Identificação", lista_plantas)
                with col2:
                    filtro_data = st.date_input("Filtrar por Data", value=None)

            df_filtrado = df.copy()
            if filtro_planta != "Todas as Plantas":
                df_filtrado = df_filtrado[df_filtrado['planta'] == filtro_planta]
            
            if filtro_data:
                df_filtrado['data'] = pd.to_datetime(df_filtrado['data']).dt.date
                df_filtrado = df_filtrado[df_filtrado['data'] == filtro_data]

            st.dataframe(df_filtrado, use_container_width=True)
            
            st.divider()
            id_del = st.number_input("ID para excluir", min_value=0)
            if st.button("Excluir Registro permanentemente"):
                excluir_registro(id_del, username)
                st.rerun()
        else:
            st.info("Nenhum dado encontrado.")

# ==========================================
# 3. TRATAMENTO DE ERROS E CADASTRO SEGURO
# ==========================================
elif authentication_status == False:
    st.error("Usuário ou senha incorretos.")
    
elif authentication_status == None:
    st.warning("AgroMonitor AI: Por favor, faça login para acessar seus dados.")
    
    st.divider()
    with st.expander("Não tem uma conta? Cadastre-se aqui"):
        with st.form("form_cadastro"):
            novo_nome = st.text_input("Nome Completo")
            novo_user = st.text_input("Nome de Usuário (login)").lower()
            nova_senha = st.text_input("Senha", type="password")
            btn_cadastrar = st.form_submit_button("Criar Conta Permanente")
            
            if btn_cadastrar:
                if novo_user in config_usuarios["usernames"]:
                    st.error("Este nome de usuário já existe! Escolha outro.")
                elif len(novo_user) < 3 or len(nova_senha) < 3:
                    st.warning("O usuário e a senha devem ter pelo menos 3 caracteres.")
                else:
                    senha_hash = stauth.Hasher([nova_senha]).generate()[0]
                    sucesso = registrar_novo_usuario(novo_user, novo_nome, senha_hash)
                    
                    if sucesso:
                        st.success("Conta criada com sucesso no Supabase! Recarregando a página...")
                        time.sleep(2)
                        st.rerun()
