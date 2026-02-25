import google.generativeai as genai  
import json
import numpy as np
from PIL import Image

def preparar_imagem_para_ia(arquivo_upload):
    img = Image.open(arquivo_upload)
    arr = np.array(img)
    if arr.dtype != np.uint8:
        arr_min, arr_max = arr.min(), arr.max()
        arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8) if arr_max > arr_min else np.zeros_like(arr, dtype=np.uint8)
    if len(arr.shape) == 3 and arr.shape[2] > 3: arr = arr[:, :, :3]
    img_rgb = Image.fromarray(arr)
    return img_rgb if img_rgb.mode == 'RGB' else img_rgb.convert('RGB')

def analisar_imagem_gemini(imagens_upload, api_key_google):
    if not api_key_google: return [{"arquivo": "Erro", "banda_identificada": "N/A", "justificativa_banda": "Falta a chave.", "nota_saude": 0, "praga_detectada": None, "diagnostico": "Cancelado."}]
    genai.configure(api_key=api_key_google)
    
    try:
        # Busca inteligente do modelo correto
        modelos_disp = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        modelo_escolhido = None
        preferencias = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-1.5-pro']
        
        for pref in preferencias:
            if pref in modelos_disp:
                modelo_escolhido = pref.replace('models/', '')
                break
                
        if not modelo_escolhido and modelos_disp:
            modelo_escolhido = modelos_disp[0].replace('models/', '')
            
        model = genai.GenerativeModel(modelo_escolhido) 
    except Exception as e: 
        return [{"arquivo": "Erro", "banda_identificada": "N/A", "justificativa_banda": f"Erro de conexão com a API: {str(e)}", "nota_saude": 0, "praga_detectada": None, "diagnostico": "Erro."}]
        
    resultados = []
    prompt = """Retorne APENAS um JSON válido e puro com esta estrutura exata: 
    {
        "banda_identificada": "Qual a banda espectral?", 
        "justificativa_banda": "Por que é essa banda?", 
        "nota_saude": 8, 
        "diagnostico": "Resumo da saúde", 
        "praga_detectada": "Nome da praga ou null"
    }"""
    
    for arquivo in imagens_upload:
        try:
            response = model.generate_content([prompt, preparar_imagem_para_ia(arquivo)])
            texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
            dados_ia = json.loads(texto_limpo)
            
            resultados.append({
                "arquivo": arquivo.name, 
                "banda_identificada": dados_ia.get("banda_identificada", "-"), 
                "justificativa_banda": dados_ia.get("justificativa_banda", "-"), 
                "nota_saude": int(dados_ia.get("nota_saude", 5)), 
                "praga_detectada": dados_ia.get("praga_detectada"), 
                "diagnostico": dados_ia.get("diagnostico", "-")
            })
        except Exception as e: 
            resultados.append({"arquivo": arquivo.name, "banda_identificada": "Erro", "justificativa_banda": str(e), "nota_saude": 0, "praga_detectada": None, "diagnostico": "Falha na análise da imagem."})
    return resultados