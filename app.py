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
    pagina = st.sidebar.radio("Navegação", ["Dashboard Analítico", "Nova Coleta de Dados", "Histórico e Mapas", "Manual e Ajuda"])
    st.sidebar.divider()
    
    # --- BUSCA AUTOMÁTICA DE CHAVES ---
    try:
        default_weather = st.secrets["OPENWEATHER_KEY"]
        default_google = st.secrets["GEMINI_API_KEY"]
    except:
        default_weather = ""
        default_google = ""
        
    weather_key = st.sidebar.text_input("OpenWeather Key", type="password", value=default_weather)
    google_key = st.sidebar.text_input("Google Gemini Key", type="password", value=default_google)
    
    # --- Variáveis de Memória ---
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
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
    # PÁGINA: NOVA COLETA
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem Múltipla")
        
        with st.container(border=True):
            st.markdown("#### 📍 Dados Gerais do Lote")
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
                st.subheader("🌦️ Clima Atual")
                if st.button("Buscar Clima", use_container_width=True):
                    d, s = get_weather_data(lat, lon, weather_key)
                    if d: st.session_state.clima_atual = {"temp": d['main']['temp'], "umid": d['main']['humidity'], "desc": d['weather'][0]['description'].title()}
                st.write(f"Temperatura: {st.session_state.clima_atual['temp']}°C | Umidade Ar: {st.session_state.clima_atual['umid']}%")

        with col_so:
            with st.container(border=True):
                st.subheader("☁️ Sensor Wi-Fi (Lote Geral)")
                if st.button("Puxar Dado do Servidor", type="primary", use_container_width=True):
                    d_wifi, msg = ler_sensor_wifi(username)
                    if d_wifi:
                        st.session_state.sensor_iot = d_wifi
                        st.success("Sincronizado!")
                    else:
                        st.error(msg)
                
                # Permite edição manual caso queira ajustar a umidade puxada
                umid_global = st.number_input("Umidade Média do Solo (%)", value=float(st.session_state.sensor_iot.get("umid", 0)))

        st.divider()

        # --- SISTEMA DINÂMICO DE AMOSTRAS ---
        st.markdown("### 🌿 Registro de Amostras (Pés)")
        
        col_add, col_rem, _ = st.columns([1, 1, 2])
        with col_add:
            if st.button("➕ Incluir Pé", use_container_width=True):
                st.session_state.num_amostras += 1
        with col_rem:
            if st.button("➖ Excluir Pé", use_container_width=True):
                if st.session_state.num_amostras > 1:
                    st.session_state.num_amostras -= 1
                else:
                    st.warning("Você precisa ter pelo menos 1 amostra.")

        dados_amostras = []
        # Exibe os campos de texto de acordo com a quantidade de amostras
        cols_amostras = st.columns(2)
        for i in range(st.session_state.num_amostras):
            col_idx = i % 2
            with cols_amostras[col_idx]:
                nome = st.text_input(f"Identificação da Amostra {i+1}", placeholder=f"Ex: Ponto {i+1}", key=f"nome_{i}")
                dados_amostras.append(nome)

        st.divider()
        
        # --- AVALIAÇÃO MANUAL MULTIESPECTRAL ---
        with st.expander("📷 Câmera Multiespectral - Notas Manuais (Opcional)"):
            st.markdown("""
            **Guia Rápido das 6 Bandas:**
            * **Azul (Blue):** Ótima para ver absorção de clorofila inicial e contagem de plantas.
            * **Verde (Green):** Reflete a saúde visual; onde a planta é mais verde, está mais vigorosa.
            * **Vermelho (Red):** Essencial para diferenciar solo nú de vegetação viva (absorve muita luz).
            * **Red Edge (Borda Vermelha):** A mais sensível ao estresse inicial; detecta problemas antes do olho humano.
            * **NIR (Infravermelho Próximo):** Refletida fortemente por plantas saudáveis; base para o cálculo de NDVI.
            * **Termal (Thermal):** Mede a temperatura da folha; excelente para detectar estresse hídrico.
            """)
            st.divider()
            
            c_banda1, c_banda2 = st.columns(2)
            with c_banda1:
                st.slider("Nota Visual: Azul/Verde/Vermelho (RGB)", 0, 10, 10)
                st.slider("Nota Visual: Borda Vermelha (Red Edge)", 0, 10, 10)
            with c_banda2:
                st.slider("Nota Visual: Infravermelho Próximo (NIR)", 0, 10, 10)
                st.slider("Nota Visual: Termal (Água)", 0, 10, 10)

        # --- UPLOAD E IA (COM INTERFACE ESTÉTICA) ---
        with st.container(border=True):
            st.subheader("🧠 Análise Geral por IA (Gemini Vision)")
            fotos = st.file_uploader("Fotos do Lote/Folhas", type=["jpg", "png", "tif", "tiff"], accept_multiple_files=True)
            
            if fotos and st.button("Analisar Imagens", type="secondary"):
                with st.spinner("Processando arquivos na nuvem..."):
                    fotos_prontas = []
                    for foto in fotos:
                        if foto.name.lower().endswith(('.tif', '.tiff')):
                            img = Image.open(foto)
                            img_array = np.array(img)
                            if img_array.dtype in [np.uint16, np.float32, np.float64]:
                                min_val, max_val = np.min(img_array), np.max(img_array)
                                if max_val > min_val:
                                    img_array = (img_array - min_val) / (max_val - min_val) * 255.0
                                img_array = img_array.astype(np.uint8)
                                img = Image.fromarray(img_array)
                            img = img.convert("RGB")
                            byte_io = io.BytesIO()
                            img.save(byte_io, format="JPEG", quality=95)
                            byte_io.name = "imagem_convertida.jpg"
                            byte_io.seek(0)
                            fotos_prontas.append(byte_io)
                        else:
                            fotos_prontas.append(foto)
                            
                    st.session_state.ai_results = analisar_imagem_gemini(fotos_prontas, google_key)
                
            # Exibição bonita dos resultados da IA
            if st.session_state.ai_results:
                st.success("Análise Finalizada com Sucesso!")
                
                # Verifica se a IA retornou uma lista de dicionários (como no seu print)
                if isinstance(st.session_state.ai_results, list):
                    for idx, resultado in enumerate(st.session_state.ai_results):
                        with st.container(border=True):
                            st.markdown(f"#### 📄 Arquivo: {resultado.get('arquivo', f'Imagem {idx+1}')}")
                            
                            c_info1, c_info2 = st.columns(2)
                            c_info1.metric("Banda Identificada", resultado.get('banda_identificada', 'N/A'))
                            c_info2.metric("Nota de Saúde (IA)", f"{resultado.get('nota_saude', '?')} / 10")
                            
                            st.info(f"**Justificativa Óptica:** {resultado.get('justificativa_banda', '')}")
                            st.write(f"**Diagnóstico Clínico:** {resultado.get('diagnostico', '')}")
                            
                            if resultado.get('praga_detectada'):
                                st.error(f"⚠️ **Alerta:** {resultado.get('praga_detectada')}")
                else:
                    # Caso a IA retorne apenas um texto simples
                    st.write(st.session_state.ai_results)

        # --- OBSERVAÇÕES E ÁUDIO ---
        st.subheader("📋 Laudo Técnico Final")
        col_notas, col_audio = st.columns([2, 1])
        with col_notas:
            nota_final = st.slider("Nota Geral Final do Lote", 0.0, 10.0, 10.0, 0.5)
            obs_texto = st.text_area("Observações de Campo", placeholder="Ex: Presença de ferrugem no talhão norte...")
        with col_audio:
            st.write("Gravação de Áudio")
            audio_gravado = mic_recorder(start_prompt="🔴 Gravar", stop_prompt="⏹️ Parar", key='gravador')
            if audio_gravado:
                st.audio(audio_gravado['bytes'])
                st.success("Áudio anexado!")

        st.divider()
        
        # --- SALVAR TODAS AS AMOSTRAS ---
        if st.button("💾 FINALIZAR E SALVAR TODAS AS AMOSTRAS", use_container_width=True, type="primary"):
            amostras_salvas = 0
            for nome_amostra in dados_amostras:
                if nome_amostra.strip() != "":
                    dados_para_salvar = {
                        "dono": username, 
                        "data": dt,
                        "hora": datetime.now().strftime("%H:%M"),
                        "planta": nome_amostra,
                        "latitude": lat,
                        "longitude": lon,
                        "clima_externo_temp": st.session_state.clima_atual['temp'],
                        "clima_externo_umid": st.session_state.clima_atual['umid'],
                        "clima_desc": st.session_state.clima_atual['desc'],
                        "sensor_local_umid": umid_global, # Pega a umidade do lote
                        "nota_geral": nota_final,
                        # Guarda as análises em JSON caso precise auditar depois
                        "ai_analise_json": json.dumps(st.session_state.ai_results) if st.session_state.ai_results else ""
                    }
                    salvar_no_banco(dados_para_salvar)
                    amostras_salvas += 1
            
            if amostras_salvas > 0:
                st.success(f"Sucesso! {amostras_salvas} amostra(s) registrada(s) no histórico!")
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

    # ------------------------------------------
    # PÁGINA: AJUDA E MANUAL
    # ------------------------------------------
    elif pagina == "Manual e Ajuda":
        st.title("📖 Manual do AgroMonitor AI")
        st.markdown("""
        Bem-vindo ao sistema de monitoramento inteligente! Abaixo você encontra as instruções de como utilizar os recursos avançados.

        ### 1. Sistema de Amostras
        Na aba **Nova Coleta**, você pode registrar múltiplas amostras de uma única vez. 
        * Defina a quantidade de pés/pontos que você está avaliando usando os botões `+` e `-`.
        * A umidade do solo lida pelo **Sensor Wi-Fi** servirá como base para todo o lote.

        ### 2. Imagens Multiespectrais (.TIF e .JPG)
        O sistema aceita imagens brutas de drones e câmeras agronômicas.
        * **NDVI e Red Edge:** Ao fazer upload, a IA tentará identificar qual filtro/banda foi usado na lente da câmera.
        * **Dica:** Fotos em .TIF pesam muito; o sistema as normaliza automaticamente para a análise da Inteligência Artificial.

        ### 3. Sincronização IoT
        Certifique-se de que o seu **ESP8266/ESP32** esteja ligado e conectado ao Wi-Fi. Ele envia os dados para o servidor global (PythonAnywhere), e o aplicativo puxa essa informação com apenas um clique.

        ### 4. Laudo em Áudio
        Se você estiver no meio do cafezal com as mãos sujas de terra, use o botão **Gravar** no final da página para registrar suas observações faladas.
        """)

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
