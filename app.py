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
from fpdf import FPDF

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
# Mostra a tela de login
authenticator.login(location='main')

# Puxa as variáveis direto da memória da nova versão do Authenticator
name = st.session_state.get("name")
authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")

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
        
    # Memória Avançada de Amostras
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
        
        if not df_dash.empty and len(df_dash) > 0 and df_dash['sensor_local_umid'].count() > 0:
            c1, c2, c3, c4 = st.columns(4)
            
            # Tratamento para evitar 'nan'
            saude_med = df_dash['nota_geral'].mean()
            umid_med = df_dash['sensor_local_umid'].mean()
            temp_med = df_dash['clima_externo_temp'].mean()
            
            saude_med = 0.0 if pd.isna(saude_med) else round(saude_med, 1)
            umid_med = 0.0 if pd.isna(umid_med) else round(umid_med, 1)
            temp_med = 0.0 if pd.isna(temp_med) else round(temp_med, 1)

            c1.metric("Total de Amostras", len(df_dash))
            c2.metric("Saúde Média", f"{saude_med} / 10")
            c3.metric("Umidade Solo Média", f"{umid_med} %")
            c4.metric("Temp. Média Ar", f"{temp_med} °C")
            
            st.divider()
            st.subheader("📍 Mapa Local de Coletas")
            df_mapa = df_dash.dropna(subset=['latitude', 'longitude'])
            if not df_mapa.empty:
                st.map(df_mapa[['latitude', 'longitude']], zoom=14, color="#00ff00")
            else:
                st.warning("Nenhuma coordenada válida para exibir no mapa.")
        else:
            st.info("Você ainda não possui coletas registradas para gerar o painel.")

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
    # PÁGINA: HISTÓRICO E MAPAS
    # ------------------------------------------
    elif pagina == "Histórico e Mapas":
        st.title("📂 Meu Histórico de Coletas")
        df = ler_banco(username) 
        
        if not df.empty:
            # --- FILTROS DE BUSCA ---
            with st.expander("🔍 Filtrar Resultados", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    lista_plantas = df['planta'].unique().tolist()
                    lista_plantas.insert(0, "Todas as Plantas")
                    filtro_planta = st.selectbox("Filtrar por Identificador", lista_plantas)
                with col2:
                    filtro_data = st.date_input("Filtrar por Data", value=None)

            # Aplicando os filtros
            df_filtrado = df.copy()
            if filtro_planta != "Todas as Plantas":
                df_filtrado = df_filtrado[df_filtrado['planta'] == filtro_planta]
            if filtro_data:
                df_filtrado['data'] = pd.to_datetime(df_filtrado['data']).dt.date
                df_filtrado = df_filtrado[df_filtrado['data'] == filtro_data]

            # --- TABELA LIMPA E ORGANIZADA ---
            st.markdown("### 📊 Dados Registrados")
            # Seleciona apenas as colunas amigáveis para o usuário ver
            colunas_visiveis = ['id', 'data', 'hora', 'planta', 'nota_geral', 'sensor_local_umid', 'clima_externo_temp', 'clima_externo_umid']
            # Filtra apenas se as colunas existirem no banco para evitar erros
            colunas_existentes = [col for col in colunas_visiveis if col in df_filtrado.columns]
            df_display = df_filtrado[colunas_existentes].copy()
            
            # Renomeia para ficar bonito na tela
            renomes = {
                'id': 'ID', 'data': 'Data', 'hora': 'Hora', 'planta': 'Identificador da Planta',
                'nota_geral': 'Saúde (0-10)', 'sensor_local_umid': 'Umidade Solo (%)',
                'clima_externo_temp': 'Temp. Ar (°C)', 'clima_externo_umid': 'Umidade Ar (%)'
            }
            df_display.rename(columns=renomes, inplace=True)
            
            # Mostra a tabela sem o índice lateral numérico (hide_index=True)
            st.dataframe(df_display, hide_index=True, use_container_width=True)
            
            # Botão de Exportar CSV
            csv = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Tabela em Excel (CSV)",
                data=csv,
                file_name=f"historico_agro_{date.today()}.csv",
                mime="text/csv",
                type="primary"
            )
            
            st.divider()
            
            # --- ZONA DE PERIGO: EXCLUSÃO ---
            with st.expander("⚠️ Gerenciamento e Exclusão de Dados"):
                c_del1, c_del2 = st.columns(2)
                
                with c_del1:
                    st.markdown("**Apagar Apenas Uma Amostra**")
                    id_del = st.number_input("Digite o ID da Amostra (veja na tabela)", min_value=0, step=1)
                    if st.button("🗑️ Apagar ID Específico"):
                        excluir_registro(id_del, username)
                        st.success(f"ID {id_del} apagado!")
                        time.sleep(1)
                        st.rerun()
                            
                with c_del2:
                    st.markdown("**Limpar Todo o Histórico**")
                    confirmacao = st.checkbox("Entendo que isso apagará todos os dados.")
                    if confirmacao:
                        if st.button("🚨 EXCLUIR TUDO", type="primary", use_container_width=True):
                            with st.spinner("Limpando banco de dados..."):
                                for id_apagar in df['id'].tolist():
                                    excluir_registro(id_apagar, username)
                            st.success("Tudo limpo!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.button("🚨 EXCLUIR TUDO", disabled=True, use_container_width=True)
        else:
            st.info("Você ainda não possui nenhum dado salvo no histórico.")

   # ------------------------------------------
    # PÁGINA: AJUDA E MANUAL
    # ------------------------------------------
    elif pagina == "Manual Prático":
        st.title("📖 Manual Prático AgroMonitor")
        st.markdown("Bem-vindo ao guia rápido de uso do seu sistema de monitoramento.")
        
        # --- FUNÇÃO QUE GERA O PDF ---
        from fpdf import FPDF

        def gerar_pdf_manual():
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, txt="Manual Pratico AgroMonitor", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", '', 12)
            # Texto sem acentos complexos para evitar bugs na fonte padrão do PDF
            texto = """
1. A Camera Multiespectral (6 Bandas)
Sua camera mede a reflectancia da luz nas folhas:
- Azul e Vermelho: Medem a fotossintese.
- Verde: Mostra o vigor natural.
- Red Edge: Detecta estresse antes da folha amarelar.
- NIR: Reflete a saude celular interna.
- Pancromatica: Imagem de altissima resolucao.

2. Inteligencia Artificial e Imagens
A IA cruza a cor da imagem com as suas notas visuais para gerar um diagnostico. Arquivos .TIF sao convertidos automaticamente.

3. Passo a Passo da Coleta
1. Va na aba 'Nova Coleta de Dados'.
2. Sincronize o Sensor Wi-Fi para puxar a umidade real.
3. Preencha o Identificador (ex: Linha 4).
4. Avalie a saude com os controles (0 a 10).
5. Anexe as fotos, gere o relatorio da IA e clique em GRAVAR.
            """
            pdf.multi_cell(0, 8, txt=texto)
            return pdf.output(dest="S").encode("latin-1")

        # --- BOTÃO DE DOWNLOAD PDF ---
        col_btn1, col_btn2 = st.columns([1, 2])
        with col_btn1:
            try:
                pdf_bytes = gerar_pdf_manual()
                st.download_button(
                    label="📄 Baixar Manual em PDF",
                    data=pdf_bytes,
                    file_name="Manual_AgroMonitor.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            except Exception as e:
                st.warning("Instale a biblioteca FPDF para baixar o PDF (`pip install fpdf`)")

        st.divider()

        # --- A SUA ORGANIZAÇÃO EM ABAS (TABS) ---
        tab1, tab2, tab3 = st.tabs([
            "📷 A Câmera Multiespectral (6 Bandas)", 
            "🤖 Inteligência Artificial e Imagens", 
            "🛠️ Passo a Passo da Coleta"
        ])
        
        with tab1:
            st.write("""
            Sua câmera não tira apenas "fotos", ela mede a reflectância da luz nas folhas (o quanto de luz a planta absorve ou rebate). Cada lente tem um papel específico:
            
            * **Azul (Blue) e Vermelho (Red):** Medem a fotossíntese. Plantas saudáveis absorvem muito azul e vermelho.
            * **Verde (Green):** É o reflexo visível. Mostra o vigor da cor natural da planta.
            * **Red Edge (Borda Vermelha):** É o seu "radar de alerta". Essa faixa detecta a perda de clorofila por doenças ou estresse hídrico *dias antes* da folha ficar amarela a olho nu.
            * **NIR (Infravermelho Próximo):** Reflete a saúde celular interna. Se a planta sofre falta de água, as células murcham e o NIR despenca.
            * **Pancromática (Lente Maior):** Tira uma foto de altíssima resolução de todas as luzes juntas para dar nitidez aos seus mapas.
            """)
            
        with tab2:
            st.write("""
            * **Arquivos .TIF:** Quando você anexa arquivos TIF da sua câmera de drone/trator, nosso sistema os converte automaticamente para um formato que a Inteligência Artificial consiga ler.
            * **Diagnóstico:** A IA cruza a cor da imagem com as notas que você forneceu para gerar um diagnóstico de pragas, falha nutricional ou estresse hídrico.
            """)
            
        with tab3:
            st.write("""
            1. Vá na aba **Nova Coleta de Dados**.
            2. Clique em **Sincronizar Sensor Wi-Fi** para puxar a umidade real do solo do seu lote.
            3. Preencha o campo **Identificador** (ex: *Linha 4 - Setor Sul*). Sem ele, o sistema não salva a amostra.
            4. Avalie a saúde da planta com os "sliders" (barrinhas de 0 a 10) para cada lente da câmera.
            5. Anexe as fotos, gere o relatório da IA, grave um áudio se precisar, e clique no botão azul **GRAVAR AMOSTRAS** no final da página.
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
