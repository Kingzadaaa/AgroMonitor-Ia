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
    pagina = st.sidebar.radio("Navegação", [
        "Dashboard Analítico", 
        "Nova Coleta de Dados", 
        "Histórico e Mapas", 
        "Manual Prático"
    ])
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
    
    # --- Variáveis de Memória (Estado do App) ---
    if "clima_atual" not in st.session_state:
        st.session_state.clima_atual = {"temp": 0.0, "umid": 0.0, "desc": "-"}
    if "sensor_iot" not in st.session_state:
        st.session_state.sensor_iot = {"umid": 0.0}
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None
        
    # Memória Avançada de Amostras
    if "amostras_dict" not in st.session_state:
        st.session_state.amostras_dict = {
            "Amostra 1": {
                "nome": "", 
                "umid": 0.0, 
                "saude": 10.0,
                # Trocado 'thermal' por 'pan'
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
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Amostras", len(df_dash))
            c2.metric("Saúde Média", f"{round(df_dash['nota_geral'].mean(), 1)} / 10")
            c3.metric("Umidade Solo Média", f"{round(df_dash['sensor_local_umid'].mean(), 1)} %")
            c4.metric("Temp. Média Ar", f"{round(df_dash['clima_externo_temp'].mean(), 1)} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            st.map(df_dash[['latitude', 'longitude']], zoom=14, color="#00ff00")
        else:
            st.info("Você ainda não possui coletas registradas.")

    # ------------------------------------------
    # PÁGINA: NOVA COLETA
    # ------------------------------------------
    elif pagina == "Nova Coleta de Dados":
        st.title("🌱 Nova Amostragem")
        
        # --- 1. DADOS GERAIS ---
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

        # --- 2. GESTÃO INDIVIDUAL DE AMOSTRAS ---
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
                else:
                    st.warning("Deixe pelo menos 1 amostra.")

        lista_chaves = list(st.session_state.amostras_dict.keys())
        with col_selecao:
            amostra_atual = st.selectbox("Selecione a amostra para preencher os dados:", lista_chaves)
        
        # O PONTUÁRIO DA AMOSTRA
        with st.container(border=True):
            st.markdown(f"#### 📝 Dados da {amostra_atual}")
            dados_atuais = st.session_state.amostras_dict[amostra_atual]
            
            c_nome, c_umid, c_saude = st.columns([2, 1, 1])
            with c_nome:
                dados_atuais["nome"] = st.text_input("Identificador (Ex: Linha 2 - Pé 4)", value=dados_atuais["nome"])
            with c_umid:
                dados_atuais["umid"] = st.number_input("Umidade do Solo (%)", value=float(dados_atuais["umid"]))
            with c_saude:
                dados_atuais["saude"] = st.slider("Saúde Visual da Planta (0 a 10)", 0.0, 10.0, float(dados_atuais["saude"]), 0.5)

            # --- AVALIAÇÃO DA CÂMERA DE 6 BANDAS ---
            with st.expander("📷 Câmera 6 Bandas - Avaliação Visual da Foto", expanded=False):
                st.markdown("Use os controles abaixo para dar a sua nota manual de saúde baseada nas imagens de cada lente da sua câmera.")
                st.divider()
                
                b1, b2, b3 = st.columns(3)
                with b1:
                    st.markdown("**🟦 Azul (Blue)**")
                    st.caption("Ajuda a diferenciar o que é planta do que é terra ou sombra.")
                    dados_atuais["notas_bandas"]["blue"] = st.slider("Nota Azul", 0, 10, int(dados_atuais["notas_bandas"]["blue"]), key=f"b_{amostra_atual}")
                    
                    st.markdown("**🟥 Vermelho (Red)**")
                    st.caption("Mostra onde a planta está absorvendo luz para fotossíntese.")
                    dados_atuais["notas_bandas"]["red"] = st.slider("Nota Vermelha", 0, 10, int(dados_atuais["notas_bandas"]["red"]), key=f"r_{amostra_atual}")
                    
                with b2:
                    st.markdown("**🟩 Verde (Green)**")
                    st.caption("O verde visível. Reflete o vigor e a cor que nossos olhos veem.")
                    dados_atuais["notas_bandas"]["green"] = st.slider("Nota Verde", 0, 10, int(dados_atuais["notas_bandas"]["green"]), key=f"g_{amostra_atual}")
                    
                    st.markdown("**🟪 Red Edge (Borda Vermelha)**")
                    st.caption("A lente dedo-duro. Detecta problemas de saúde antes da folha amarelar.")
                    dados_atuais["notas_bandas"]["rededge"] = st.slider("Nota Red Edge", 0, 10, int(dados_atuais["notas_bandas"]["rededge"]), key=f"re_{amostra_atual}")
                    
                with b3:
                    st.markdown("**🟫 NIR (Infravermelho Próx.)**")
                    st.caption("Mostra a saúde interna da folha. Brilha muito quando a planta está sadia.")
                    dados_atuais["notas_bandas"]["nir"] = st.slider("Nota NIR", 0, 10, int(dados_atuais["notas_bandas"]["nir"]), key=f"n_{amostra_atual}")
                    
                    st.markdown("**📸 Pancromática (Lente Maior)**")
                    st.caption("Captura a imagem geral em altíssima resolução para dar nitidez aos mapas.")
                    dados_atuais["notas_bandas"]["pan"] = st.slider("Nota Pancromática", 0, 10, int(dados_atuais["notas_bandas"]["pan"]), key=f"p_{amostra_atual}")

        st.divider()

        # --- 3. UPLOAD E IA ---
        with st.container(border=True):
            st.subheader("🧠 IA Gemini Vision")
            st.write("Anexe as fotos da câmera (.TIF) ou normais (.JPG). A IA fará a leitura e conversão automática.")
            fotos = st.file_uploader("Arquivos de Imagem", type=["jpg", "png", "tif", "tiff"], accept_multiple_files=True)
            
            if fotos and st.button("Gerar Diagnóstico por IA", type="secondary"):
                with st.spinner("Processando imagens..."):
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
                
            if st.session_state.ai_results:
                st.success("Análise Finalizada!")
                if isinstance(st.session_state.ai_results, list):
                    for idx, resultado in enumerate(st.session_state.ai_results):
                        with st.container(border=True):
                            st.markdown(f"#### 📄 Arquivo: {resultado.get('arquivo', f'Imagem {idx+1}')}")
                            c_info1, c_info2 = st.columns(2)
                            c_info1.metric("Banda Identificada", resultado.get('banda_identificada', 'N/A'))
                            c_info2.metric("Saúde Avaliada (IA)", f"{resultado.get('nota_saude', '?')} / 10")
                            st.info(f"**Justificativa Visual:** {resultado.get('justificativa_banda', '')}")
                            st.write(f"**Diagnóstico:** {resultado.get('diagnostico', '')}")
                            if resultado.get('praga_detectada'):
                                st.error(f"⚠️ **Alerta:** {resultado.get('praga_detectada')}")
                else:
                    st.write(st.session_state.ai_results)

        # --- 4. OBSERVAÇÕES E ÁUDIO ---
        st.subheader("📋 Observações Complementares")
        col_notas, col_audio = st.columns([2, 1])
        with col_notas:
            obs_texto = st.text_area("Anotações de Campo", placeholder="Descreva qualquer detalhe extra encontrado na parcela...")
        with col_audio:
            st.write("Gravar Mensagem de Voz")
            audio_gravado = mic_recorder(start_prompt="🔴 Gravar", stop_prompt="⏹️ Parar", key='gravador')
            if audio_gravado:
                st.audio(audio_gravado['bytes'])
                st.success("Áudio anexado!")

        st.divider()
        
        # --- 5. SALVAR TUDO ---
        if st.button("💾 GRAVAR AMOSTRAS NO BANCO DE DADOS", use_container_width=True, type="primary"):
            amostras_salvas = 0
            for chave, dados_amostra in st.session_state.amostras_dict.items():
                if dados_amostra["nome"].strip() != "":
                    dados_para_salvar = {
                        "dono": username, 
                        "data": dt,
                        "hora": datetime.now().strftime("%H:%M"),
                        "planta": dados_amostra["nome"],
                        "latitude": lat,
                        "longitude": lon,
                        "clima_externo_temp": st.session_state.clima_atual['temp'],
                        "clima_externo_umid": st.session_state.clima_atual['umid'],
                        "clima_desc": st.session_state.clima_atual['desc'],
                        "sensor_local_umid": dados_amostra["umid"], 
                        "nota_geral": dados_amostra["saude"],
                        "ai_analise_json": json.dumps({
                            "observacao_texto": obs_texto,
                            "notas_bandas": dados_amostra["notas_bandas"],
                            "ia_resultado": st.session_state.ai_results
                        })
                    }
                    salvar_no_banco(dados_para_salvar)
                    amostras_salvas += 1
            
            if amostras_salvas > 0:
                st.success(f"Show! {amostras_salvas} amostra(s) salvas no seu histórico.")
                st.session_state.ai_results = None 
            else:
                st.warning("Aviso: Preencha o campo 'Identificador' da amostra antes de salvar.")

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
                    filtro_planta = st.selectbox("Filtrar por Identificador", lista_plantas)
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
            
            # --- ZONA DE PERIGO: EXCLUSÃO ---
            st.markdown("### ⚠️ Gerenciamento de Dados")
            c_del1, c_del2 = st.columns(2)
            
            with c_del1:
                with st.container(border=True):
                    st.write("**Apagar Apenas Uma Amostra**")
                    id_del = st.number_input("ID da Amostra", min_value=0)
                    if st.button("🗑️ Apagar ID"):
                        excluir_registro(id_del, username)
                        st.rerun()
                        
            with c_del2:
                with st.container(border=True):
                    st.write("**Limpar Tudo**")
                    confirmacao = st.checkbox("Sim, quero apagar todos os meus dados.")
                    if confirmacao:
                        if st.button("🚨 EXCLUIR MEU HISTÓRICO COMPLETO", type="primary", use_container_width=True):
                            with st.spinner("Limpando banco de dados..."):
                                for id_apagar in df['id'].tolist():
                                    excluir_registro(id_apagar, username)
                            st.success("Tudo limpo!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.button("🚨 EXCLUIR MEU HISTÓRICO COMPLETO", disabled=True, use_container_width=True)
        else:
            st.info("Nenhum dado salvo ainda.")

    # ------------------------------------------
    # PÁGINA: AJUDA E MANUAL
    # ------------------------------------------
    elif pagina == "Manual Prático":
        st.title("📖 Manual do Sistema")
        
        with st.expander("📷 A Câmera de 6 Bandas", expanded=True):
            st.write("""
            Sua câmera multiespectral tem funções específicas em cada lente para ajudar no diagnóstico agrícola:
            
            * **Azul (Blue):** Bom para separar o que é planta do que é sombra ou terra no chão.
            * **Verde (Green):** É a cor natural da planta. Ajuda a ver o vigor geral igual nossos olhos veem.
            * **Vermelho (Red):** Mostra onde a planta está forte fazendo fotossíntese.
            * **Red Edge (Borda Vermelha):** É o raio-x da saúde. Ela avisa que a planta está doente ou estressada muito antes da folha ficar amarela.
            * **Infravermelho Próximo (NIR):** Reflete a saúde das células por dentro da folha. Brilha forte quando a planta está bem hidratada e sadia. É muito usada para gerar o mapa NDVI.
            * **Pancromática (A Lente Maior):** Captura toda a luz de uma vez em altíssima resolução. O sistema usa essa imagem para dar "foco" e muita nitidez aos mapas gerados pelas outras lentes menores.
            """)
            
        with st.expander("⚙️ Como Funciona o Envio de Dados", expanded=True):
            st.write("""
            1. **Sensor no Campo:** O sensor pega a umidade do solo e manda via Wi-Fi para o servidor.
            2. **O Aplicativo:** Quando você aperta "Sincronizar", ele puxa esse número direto para a tela, preenchendo as amostras.
            3. **As Fotos:** Ao enviar imagens da sua câmera (.TIF) para o sistema, ele formata as cores automaticamente para a Inteligência Artificial conseguir "enxergar" e devolver a nota e os possíveis problemas do lote.
            """)

# ==========================================
# 3. TRATAMENTO DE ERROS E CADASTRO SEGURO
# ==========================================
elif authentication_status == False:
    st.error("Usuário ou senha incorretos. Acesso negado.")
    
elif authentication_status == None:
    st.warning("AgroMonitor: Faça o login para acessar o sistema.")
    
    st.divider()
    with st.expander("Ainda não tem conta? Cadastre-se"):
        with st.form("form_cadastro"):
            novo_nome = st.text_input("Seu Nome")
            novo_user = st.text_input("Nome de Usuário (Login)").lower()
            nova_senha = st.text_input("Sua Senha", type="password")
            btn_cadastrar = st.form_submit_button("Criar Conta")
            
            if btn_cadastrar:
                if novo_user in config_usuarios["usernames"]:
                    st.error("Esse usuário já existe, tente outro.")
                elif len(novo_user) < 3 or len(nova_senha) < 3:
                    st.warning("O usuário e a senha precisam ter pelo menos 3 letras/números.")
                else:
                    senha_hash = stauth.Hasher([nova_senha]).generate()[0]
                    sucesso = registrar_novo_usuario(novo_user, novo_nome, senha_hash)
                    
                    if sucesso:
                        st.success("Conta criada! Pode fazer o login.")
                        time.sleep(2)
                        st.rerun()
