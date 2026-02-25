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
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            texto = response.text
            
            # Método infalível: cortando o HTML para pegar o valor exato
            if 'class="umid">' in texto:
                pedaco = texto.split('class="umid">')[1]
                valor_bruto = pedaco.split('</div>')[0].replace('%', '').strip()
                
                try:
                    umidade_valor = float(valor_bruto)
                    return {"umid": umidade_valor}, "Sucesso"
                except ValueError:
                    # Se não for um número, ele vai nos dedurar o que é!
                    return None, f"O sensor não enviou o número. O site diz: '{valor_bruto}'"
            else:
                return None, "Não encontrou a caixinha de umidade no código do site."
        else:
            return None, f"Erro no servidor: {response.status_code}"
    except Exception as e:
        return None, f"Erro de conexão com sensor: {str(e)}"

