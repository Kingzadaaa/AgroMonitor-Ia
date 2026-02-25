import requests
import serial
import serial.tools.list_ports
import re

def get_weather_data(lat, lon, api_key):
    if not api_key:
        return None, "Chave da API de Clima não fornecida"
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        resposta = requests.get(url, timeout=5)
        if resposta.status_code == 200:
            return resposta.json(), "Sucesso"
        return None, f"Erro na API de Clima: {resposta.status_code}"
    except Exception as e:
        return None, f"Erro de conexão com Clima: {e}"

def listar_portas_com():
    portas = serial.tools.list_ports.comports()
    return [porta.device for porta in portas]

def ler_sensor_esp(porta):
    # Função mantida para compatibilidade local via cabo USB
    pass

def ler_sensor_wifi(usuario_logado):
    """Busca a umidade do usuário específico no PythonAnywhere"""
    url = f"https://MarcoAntonio2026.pythonanywhere.com/?usuario={usuario_logado}"
    
    try:
        response = requests.get(url, timeout=10) # Aumentei o tempo de espera
        if response.status_code == 200:
            texto = response.text
            # Essa linha caça qualquer número (com ou sem ponto decimal) antes do %
            match = re.search(r'class="umid">\s*([0-9.]+)\s*%', texto)
            
            if match:
                umidade_valor = float(match.group(1))
                return {"umid": umidade_valor}, "Sucesso"
            else:
                return None, "Dado não encontrado na tela do servidor."
        else:
            return None, f"Erro no servidor: {response.status_code}"
    except Exception as e:
        return None, f"Erro de conexão com sensor: {str(e)}"
