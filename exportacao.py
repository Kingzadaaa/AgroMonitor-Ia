from fpdf import FPDF
import pandas as pd

def gerar_laudo_pdf(linha):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho Centralizado
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "LAUDO TECNICO DE SENSORIAMENTO E I.A.", ln=True, align='C')
    pdf.ln(5)
    
    # Dados da Amostra
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Identificacao da Amostra: {linha['planta']}", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, f"Data da Coleta: {linha['data']} as {linha['hora']}", ln=True)
    pdf.cell(0, 8, f"Coordenadas Geograficas: Lat {linha['latitude']} | Lon {linha['longitude']}", ln=True)
    pdf.ln(5)
    
    # Condições Edafoclimáticas (Texto Justificado)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Condicoes Edafoclimaticas", ln=True)
    pdf.set_font("Arial", '', 11)
    texto_clima = f"No momento da coleta, a temperatura externa local era de {linha['clima_externo_temp']} graus Celsius, com umidade relativa do ar em {linha['clima_externo_umid']}%. O sensor de solo registrou uma umidade volumetrica radicular de {linha['sensor_local_umid']}%. O avaliador humano atribuiu a nota global de sanidade de {linha['nota_geral']}/10."
    pdf.multi_cell(0, 8, texto_clima, align='J')
    pdf.ln(5)
    
    # Observações Humanas
    if linha['observacao']:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "2. Observacoes de Campo", ln=True)
        pdf.set_font("Arial", '', 11)
        pdf.multi_cell(0, 8, linha['observacao'], align='J')
    
    return pdf.output(dest='S').encode('latin-1')

def gerar_kml_google_earth(df_mapa):
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Mapa AgroMonitor</name>
    <Style id="pVerde"><IconStyle><Icon><href>http://maps.google.com/mapfiles/ms/icons/green-dot.png</href></Icon></IconStyle></Style>
    <Style id="pAmarelo"><IconStyle><Icon><href>http://maps.google.com/mapfiles/ms/icons/yellow-dot.png</href></Icon></IconStyle></Style>
    <Style id="pVermelho"><IconStyle><Icon><href>http://maps.google.com/mapfiles/ms/icons/red-dot.png</href></Icon></IconStyle></Style>"""
    for _, row in df_mapa.iterrows():
        estilo = "#pVerde" if row['nota_geral'] >= 7 else "#pAmarelo" if row['nota_geral'] >= 5 else "#pVermelho"
        kml += f"""<Placemark><name>{row['planta']}</name><styleUrl>{estilo}</styleUrl>
        <description>Saúde: {row['nota_geral']}/10</description>
        <Point><coordinates>{row['longitude']},{row['latitude']},0</coordinates></Point></Placemark>"""
    kml += "</Document></kml>"
    return kml.encode('utf-8')