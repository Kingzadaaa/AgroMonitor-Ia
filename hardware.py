import requests
import re
import serial
import serial.tools.list_ports
import json

def get_weather_data(lat, lon, api_key):
    if not api_key: return None, "Chave de API ausente."
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        r = requests.get(url)
        return (r.json(), "Conexão estabelecida") if r.status_code == 200 else (None, f"Erro: {r.status_code}")
    except Exception as e: return None, str(e)

def listar_portas_com(): 
    return [p.device for p in serial.tools.list_ports.comports()]

def ler_sensor_esp(porta):
    try:
        ser = serial.Serial(porta, 115200, timeout=2)
        line = ser.readline().decode().strip() or ser.readline().decode().strip()
        ser.close()
        return json.loads(line), "Sucesso"
    except Exception as e: return None, str(e)

# ==========================================
# NOVA FUNÇÃO: LER O SENSOR VIA WI-FI (NUVEM)
# ==========================================
import requests

def ler_sensor_wifi(usuario_logado):
    """
    Busca a umidade do sensor específico do usuário logado no servidor em nuvem.
    """
    # Note que agora passamos o ?usuario= no final da URL
    url = f"https://MarcoAntonio2026.pythonanywhere.com/?usuario={usuario_logado}"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            # Vamos usar uma técnica simples para "caçar" o número dentro do HTML
            import re
            texto = response.text
            # Procura pelo número que está dentro da div com classe 'umid'
            match = re.search(r'class="umid">(\d+)%', texto)
            
            if match:
                umidade_valor = match.group(1)
                return {"umid": float(umidade_valor)}, "Sucesso"
            else:
                return None, "Sensor ainda não enviou dados."
        else:
            return None, f"Erro no servidor: {response.status_code}"
    except Exception as e:
        return None, f"Erro de conexão: {str(e)}"