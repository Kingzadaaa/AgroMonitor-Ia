import streamlit as st
import streamlit_authenticator as stauth
from datetime import date, datetime
import json
import os

# --- Importando seus módulos personalizados ---
# Note que removemos o 'deletar_todo_historico' que não está mais no banco.py
from banco import salvar_no_banco, ler_banco, excluir_registro, salvar_bytes_audio
from hardware import get_weather_data, listar_portas_com, ler_sensor_esp, ler_sensor_wifi
from ia_core import analisar_imagem_gemini, preparar_imagem_para_ia
from exportacao import gerar_kml_google_earth, gerar_laudo_pdf
from streamlit_mic_recorder import mic_recorder

# ==========================================
# 1. SISTEMA DE AUTENTICAÇÃO (LOGIN)
# ==========================================
config_usuarios = {
    "usernames": {
        "marco": {
            "name": "Marco Antonio",
            "password": "123" 
        },
        "agronomo": {
            "name": "Consultor Tecnico",
            "password": "456"
        }
    }
}

authenticator = stauth.Authenticate(
    config_usuarios,
    "agromonitor_cookie",
    "agromonitor_key",
    cookie_expiry_days=30
)

# AJUSTE DA LINHA 41: Agora usando o parâmetro nomeado 'location'
st.write("#") # Espaçamento topo
name, authentication_status, username = authenticator.login(location='main')

# ==========================================
# 2. ÁREA RESTRITA (SÓ ENTRA SE LOGAR)
# ==========================================
if authentication_status:
    # --- Configuração da Página ---
    st.sidebar.title(f"Olá, {name}!")
    authenticator.logout("Sair do Sistema", "sidebar")
    
    st.sidebar.divider()
    pagina = st.sidebar.radio("Navegação", ["Dashboard Analítico", "Nova Coleta de Dados", "Histórico e Mapas", "Ajuda"])
    st.sidebar.divider()
    
    weather_key = st.sidebar.text_input("OpenWeather Key", type="password")
    google_key = st.sidebar.text_input("Google Gemini Key", type="password")
    
    # Inicializações de Memória de Sessão
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None

    # ------------------------------------------
    # PÁGINA: DASHBOARD
    # ------------------------------------------
    if pagina == "Dashboard Analítico":
        st.title(f"📊 Painel de Controle: {name}")
        df_dash = ler_banco(username) 
        
        if not df_dash.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Minhas Amostras", len(df_dash))
            c2.metric("Saúde Média", f"{round(df_dash['nota_geral'].mean(), 1)} / 10")
            c3.metric("Umidade Solo Média", f"{round(df_dash['sensor_local_umid'].mean(), 1)} %")
            c4.metric("Temp. Média Ar", f"{round(df_dash['clima_externo_temp'].mean(), 1)} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            st.map(df_dash[['latitude', 'longitude']], zoom=14, color="#00ff00")
        else:
            st.info("Você ainda não possui coletas registradas no Supabase.")

    # ------------------------------------------
    # PÁGINA: NOVA COLETA
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem")
        
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                planta_nome = st.text_input("Identificação da Planta/Lote", placeholder="Ex: Café Arábica - Quadra 4")
                dt = st.date_input("Data", date.today())
            with c2:
                lat = st.number_input("Latitude", value=-20.91, format="%.6f")
                lon = st.number_input("Longitude", value=-46.98, format="%.6f")

        col_cl, col_so = st.columns(2)
        with col_cl:
            with st.container(border=True):
                st.subheader("🌦️ Clima")
                if st.button("Buscar Clima", use_container_width=True):
                    d, s = get_weather_data(lat, lon, weather_key)
                    if d: st.session_state.clima_atual = {"temp": d['main']['temp'], "umid": d['main']['humidity'], "desc": d['weather'][0]['description'].title()}
                st.write(f"Temp: {st.session_state.clima_atual['temp']}°C | Umid: {st.session_state.clima_atual['umid']}%")

       # No app.py, dentro da página "Nova Coleta de Dados"
with col_so:
    with st.container(border=True):
        st.subheader("☁️ Sensor Wi-Fi")
        if st.button("Sincronizar Nuvem", type="primary", use_container_width=True):
            # AGORA PASSAMOS O USERNAME LOGADO AQUI
            d_wifi, msg = ler_sensor_wifi(username) 
            if d_wifi:
                st.session_state.sensor_iot = d_wifi
                st.success(f"Sincronizado para o usuário: {username}!")
            else:
                st.error(msg)

        with st.container(border=True):
            st.subheader("🧠 Análise por IA")
            fotos = st.file_uploader("Fotos da Planta", type=["jpg", "png"], accept_multiple_files=True)
            if fotos and st.button("Analisar com Gemini"):
                st.session_state.ai_results = analisar_imagem_gemini(fotos, google_key)
                st.success("Análise Finalizada!")

        st.divider()
        if st.button("💾 FINALIZAR E SALVAR NO SUPABASE", use_container_width=True, type="primary"):
            dados_para_salvar = {
                "dono": username, 
                "data": dt,
                "hora": datetime.now().strftime("%H:%M"),
                "planta": planta_nome,
                "latitude": lat,
                "longitude": lon,
                "clima_externo_temp": st.session_state.clima_atual['temp'],
                "clima_externo_umid": st.session_state.clima_atual['umid'],
                "clima_desc": st.session_state.clima_atual['desc'],
                "sensor_local_umid": s_umid,
                "nota_geral": 10,
                "ai_analise_json": json.dumps(st.session_state.ai_results) if st.session_state.ai_results else ""
            }
            salvar_no_banco(dados_para_salvar)
            st.success("Coleta registrada com sucesso na sua conta!")

   # ... (código anterior da Nova Coleta)
    
    # ------------------------------------------
    # PÁGINA: HISTÓRICO
    # ------------------------------------------
    elif pagina == "Histórico e Mapas":
        st.title("📂 Meu Histórico")
        df = ler_banco(username) 
        st.dataframe(df, use_container_width=True)
        
        if not df.empty:
            id_del = st.number_input("ID para excluir", min_value=0)
            if st.button("Excluir Registro permanentemente"):
                excluir_registro(id_del, username)
                st.rerun()

# --- ATENÇÃO: Estes últimos elifs devem estar alinhados com o primeiro 'if authentication_status' ---
elif authentication_status == False:
    st.error("Usuário ou senha incorretos.")
elif authentication_status == None:
    st.warning("AgroMonitor AI: Por favor, faça login para acessar seus dados.")

# ==========================================
# 3. TRATAMENTO DE ERROS DE LOGIN
# ==========================================
elif authentication_status == False:
    st.error("Usuário ou senha incorretos.")
elif authentication_status == None:
    st.warning("AgroMonitor AI: Por favor, faça login para acessar seus dados.")