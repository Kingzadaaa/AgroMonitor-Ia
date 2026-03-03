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
# Certifique-se de que esses arquivos existem no seu repositório
from banco import salvar_no_banco, ler_banco, excluir_registro, salvar_bytes_audio, ler_usuarios_supabase, registrar_novo_usuario
from hardware import get_weather_data, listar_portas_com, ler_sensor_esp, ler_sensor_wifi
from ia_core import analisar_imagem_gemini
from streamlit_mic_recorder import mic_recorder

#Configuração da página (deve ser o primeiro comando Streamlit)
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
    
    # --- ENTRADA MANUAL DE CHAVES ---
    weather_key = st.sidebar.text_input("OpenWeather Key", type="password")
    google_key = st.sidebar.text_input("Google Gemini Key", type="password")
    
    # --- Variáveis de Memória (Estado do App) ---
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
        
    if "amostras_dict" not in st.session_state:
        st.session_state.amostras_dict = {
            "Amostra 1": {
                "nome": "", 
                "umid": 0.0, 
                "saude": 10.0,
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
            # Padronizar colunas para minúsculo para evitar erros de exibição
            df_dash.columns = [c.lower() for c in df_dash.columns]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Amostras", len(df_dash))
            if 'nota_geral' in df_dash.columns:
                c2.metric("Saúde Média", f"{round(df_dash['nota_geral'].mean(), 1)} / 10")
            if 'sensor_local_umid' in df_dash.columns:
                c3.metric("Umidade Solo Média", f"{round(df_dash['sensor_local_umid'].mean(), 1)} %")
            if 'clima_externo_temp' in df_dash.columns:
                c4.metric("Temp. Média Ar", f"{round(df_dash['clima_externo_temp'].mean(), 1)} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            if 'latitude' in df_dash.columns and 'longitude' in df_dash.columns:
                st.map(df_dash[['latitude', 'longitude']], zoom=14, color="#00ff00")
        else:
            st.info("Você ainda não possui coletas registradas.")

    # ------------------------------------------
    # PÁGINA: NOVA COLETA
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem")
        
        with st.container(border=True):
            st.markdown("#### 📍 Clima e Localização")
            c1, c2, c3 = st.columns(3)
            with c1:
                dt = st.date_input("Data da Coleta", date.today())
            with c2:
                lat = st.number_input("Latitude Base", value=-20.91, format="%.6f")
            with c3:
                lon = st.number_input("Longitude Base", value=-46.98, format="%.6f")

        col_cl, col_so = st.columns(2)
        with col_cl:
            with st.container(border=True):
                st.subheader("🌦️ Estação Meteorológica")
                if st.button("Buscar Clima via Satélite", use_container_width=True):
                    d, s = get_weather_data(lat, lon, weather_key)
                    if d: st.session_state.clima_atual = {"temp": d['main']['temp'], "umid": d['main']['humidity'], "desc": d['weather'][0]['description'].title()}
                st.write(f"Temperatura: {st.session_state.clima_atual['temp']}°C | Umidade Ar: {st.session_state.clima_atual['umid']}%")

        with col_so:
            with st.container(border=True):
                st.subheader("☁️ Sensor IoT (Lote)")
                if st.button("Sincronizar Sensor Wi-Fi", type="primary", use_container_width=True):
                    d_wifi, msg = ler_sensor_wifi(username)
                    if d_wifi:
                        st.session_state.sensor_iot = d_wifi
                        if "Amostra 1" in st.session_state.amostras_dict:
                            st.session_state.amostras_dict["Amostra 1"]["umid"] = float(d_wifi.get("umid", 0))
                        st.success("Dados recebidos da Nuvem!")
                    else:
                        st.error(msg)
                st.write(f"Última leitura de base: {st.session_state.sensor_iot.get('umid', 0)} %")

        st.divider()

        # --- GESTÃO DE AMOSTRAS ---
        st.markdown("### 🌿 Gestão de Amostras")
        col_selecao, col_add, col_rem = st.columns([2, 1, 1])
        with col_add:
            if st.button("➕ Criar Nova Amostra", use_container_width=True):
                nova_chave = f"Amostra {len(st.session_state.amostras_dict) + 1}"
                st.session_state.amostras_dict[nova_chave] = {
                    "nome": "", 
                    "umid": float(st.session_state.sensor_iot.get("umid", 0)), 
                    "saude": 10.0,
                    "notas_bandas": {"blue": 10, "green": 10, "red": 10, "rededge": 10, "nir": 10, "pan": 10}
                }
                st.rerun()
        with col_rem:
            if st.button("➖ Remover Última", use_container_width=True):
                if len(st.session_state.amostras_dict) > 1:
                    ultima_chave = list(st.session_state.amostras_dict.keys())[-1]
                    del st.session_state.amostras_dict[ultima_chave]
                    st.rerun()

        lista_chaves = list(st.session_state.amostras_dict.keys())
        with col_selecao:
            amostra_atual = st.selectbox("Selecione a amostra:", lista_chaves)
        
        with st.container(border=True):
            dados_atuais = st.session_state.amostras_dict[amostra_atual]
            c_nome, c_umid, c_saude = st.columns([2, 1, 1])
            with c_nome:
                dados_atuais["nome"] = st.text_input("Identificador (Ex: Linha 2)", value=dados_atuais["nome"])
            with c_umid:
                dados_atuais["umid"] = st.number_input("Umidade (%)", value=float(dados_atuais["umid"]))
            with c_saude:
                dados_atuais["saude"] = st.slider("Saúde (0-10)", 0.0, 10.0, float(dados_atuais["saude"]))

            with st.expander("📷 Avaliação 6 Bandas"):
                b1, b2, b3 = st.columns(3)
                with b1:
                    dados_atuais["notas_bandas"]["blue"] = st.slider("Azul", 0, 10, int(dados_atuais["notas_bandas"]["blue"]), key=f"b_{amostra_atual}")
                    dados_atuais["notas_bandas"]["red"] = st.slider("Vermelho", 0, 10, int(dados_atuais["notas_bandas"]["red"]), key=f"r_{amostra_atual}")
                with b2:
                    dados_atuais["notas_bandas"]["green"] = st.slider("Verde", 0, 10, int(dados_atuais["notas_bandas"]["green"]), key=f"g_{amostra_atual}")
                    dados_atuais["notas_bandas"]["rededge"] = st.slider("Red Edge", 0, 10, int(dados_atuais["notas_bandas"]["rededge"]), key=f"re_{amostra_atual}")
                with b3:
                    dados_atuais["notas_bandas"]["nir"] = st.slider("NIR", 0, 10, int(dados_atuais["notas_bandas"]["nir"]), key=f"n_{amostra_atual}")
                    dados_atuais["notas_bandas"]["pan"] = st.slider("Pancromática", 0, 10, int(dados_atuais["notas_bandas"]["pan"]), key=f"p_{amostra_atual}")

        # --- UPLOAD E IA ---
        fotos = st.file_uploader("Imagens (.JPG, .TIF)", type=["jpg", "png", "tif", "tiff"], accept_multiple_files=True)
        if fotos and st.button("Gerar Diagnóstico IA"):
            with st.spinner("Analisando..."):
                st.session_state.ai_results = analisar_imagem_gemini(fotos, google_key)

        # --- SALVAR ---
        obs_texto = st.text_area("Anotações")
        if st.button("💾 SALVAR NO BANCO", type="primary"):
            for chave, d_am in st.session_state.amostras_dict.items():
                if d_am["nome"].strip():
                    payload = {
                        "dono": username, "data": dt, "hora": datetime.now().strftime("%H:%M"),
                        "planta": d_am["nome"], "latitude": lat, "longitude": lon,
                        "clima_externo_temp": st.session_state.clima_atual['temp'],
                        "sensor_local_umid": d_am["umid"], "nota_geral": d_am["saude"],
                        "ai_analise_json": json.dumps({"notas_bandas": d_am["notas_bandas"], "ia": st.session_state.ai_results})
                    }
                    salvar_no_banco(payload)
            st.success("Salvo!")

    # ------------------------------------------
    # PÁGINA: HISTÓRICO
    # ------------------------------------------
    elif pagina == "Histórico e Mapas":
        st.title("📂 Histórico")
        df = ler_banco(username)
        
        if not df.empty:
            df.columns = [c.lower() for c in df.columns] # Correção de KEYERROR
            st.dataframe(df, use_container_width=True)
            
            st.divider()
            st.subheader("⚠️ Gerenciar Dados")
            c_del1, c_del2 = st.columns(2)
            
            with c_del1:
                id_del = st.number_input("ID para apagar", min_value=0)
                if st.button("🗑️ Apagar ID"):
                    excluir_registro(id_del, username)
                    st.rerun()
            
            with c_del2:
                confirmar = st.checkbox("Confirmar exclusão total")
                if confirmar:
                    if st.button("🚨 LIMPAR TUDO", type="primary"):
                        for id_at in df['id'].tolist():
                            excluir_registro(id_at, username)
                        st.rerun()
        else:
            st.info("Sem dados.")

    elif pagina == "Manual Prático":
        st.title("📖 Manual")
        st.write("Consulte as instruções de uso da câmera multiespectral e sensores.")

# ==========================================
# 3. LOGIN E CADASTRO
# ==========================================
elif authentication_status == False:
    st.error("Erro no login.")
elif authentication_status == None:
    st.warning("AgroMonitor: Faça o login.")
    with st.expander("Cadastre-se"):
        with st.form("cadastro"):
            n_nome = st.text_input("Nome")
            n_user = st.text_input("Usuário").lower()
            n_pass = st.text_input("Senha", type="password")
            if st.form_submit_button("Criar"):
                h_pass = stauth.Hasher([n_pass]).generate()[0]
                if registrar_novo_usuario(n_user, n_nome, h_pass):
                    st.success("Criado!")
                    time.sleep(1)
                    st.rerun()
