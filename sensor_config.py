# -*- coding: utf-8 -*-
"""
CONFIGURAÇÃO DE SENSORES IOT REAIS - VERSÃO ATUALIZADA
=======================================================
Suporte para múltiplos protocolos e configurações API distintas

✨ NOVIDADES v2.2:
- Suporte para múltiplas configurações HTTP (várias APIs)
- Routing automático baseado em api_config
- Coluna api_config no Excel para máxima flexibilidade
- MQTT preparado arquiteturalmente (não implementado funcionalmente)
"""


# ==========================================
# MÚLTIPLAS CONFIGURAÇÕES HTTP/REST API
# ==========================================
# Define várias APIs REST diferentes
# Útil para sensores de fabricantes diferentes

HTTP_CONFIGS = {
    # API NCD Industrial IoT
    'ncd_api': {
        'base_url': 'https://api.ncd.io/v1',
        'api_key': 'SEU_API_KEY_NCD_AQUI',
        'timeout': 10,
        'endpoints': {
            'temperature': '/sensors/{sensor_id}/temperature',
            'humidity': '/sensors/{sensor_id}/humidity',
            'co2': '/sensors/{sensor_id}/co2'
        }
    },
    
    # API Adeunis IoT
    'adeunis_api': {
        'base_url': 'https://api.adeunis.com/v2',
        'api_key': 'SEU_API_KEY_ADEUNIS_AQUI',
        'timeout': 10,
        'endpoints': {
            'temperature': '/devices/{sensor_id}/temp',
            'humidity': '/devices/{sensor_id}/hum',
            'co2': '/devices/{sensor_id}/co2'
        }
    },
    
    # Gateway local (ex: Pressac Solar Gateway)
    'local_gateway': {
        'base_url': 'http://192.168.1.50:8080',
        'api_key': '',  # Sem API key
        'timeout': 5,
        'endpoints': {
            'temperature': '/api/v1/sensors/{sensor_id}/temp',
            'humidity': '/api/v1/sensors/{sensor_id}/hum',
            'co2': '/api/v1/sensors/{sensor_id}/co2',
            'illuminance': '/api/v1/sensors/{sensor_id}/light'
        }
    }
}


# ==========================================
# CONFIGURAÇÕES MQTT (PREPARADO - NÃO IMPLEMENTADO)
# ==========================================
# ⚠️ ATENÇÃO: Configurações MQTT estão PREPARADAS arquiteturalmente
# mas NÃO IMPLEMENTADAS funcionalmente no código.
#
# Para IMPLEMENTAR, seria necessário:
# 1. Instalar: pip install paho-mqtt
# 2. Criar subscriber em ifc_iot_server.py (~50-80 linhas)
# 3. Iniciar broker MQTT (Mosquitto/HiveMQ)
#
# Não foi implementado por:
# - Foco da dissertação é Prompt Engineering, não protocolos IoT
# - HTTP polling suficiente para escala teste (~20 sensores)
# - MQTT brilha com >100 sensores e latência <10s

MQTT_CONFIGS = {
    # Broker Mosquitto local
    'mosquitto_local': {
        'broker': 'localhost',
        'port': 1883,
        'username': '',  # Opcional
        'password': '',  # Opcional
        'client_id': 'vivienda_subscriber',
        'qos': 1,  # Quality of Service (0, 1, 2)
        'topics': {
            'temperature': 'building/+/temperature',  # + é wildcard para qualquer espaço
            'humidity': 'building/+/humidity',
            'co2': 'building/+/co2',
            'all_sensors': 'building/#'  # # é wildcard multi-nível
        }
    },
    
    # Broker HiveMQ Cloud (exemplo cloud)
    'hivemq_cloud': {
        'broker': 'broker.hivemq.com',
        'port': 1883,
        'username': 'SEU_USERNAME_HIVEMQ',
        'password': 'SEU_PASSWORD_HIVEMQ',
        'client_id': 'vivienda_cloud',
        'qos': 1,
        'topics': {
            'temperature': 'vivienda/sensors/+/temp',
            'humidity': 'vivienda/sensors/+/hum',
            'co2': 'vivienda/sensors/+/co2'
        }
    }
}


# ==========================================
# CONFIGURAÇÃO DE MOCK DATA (SIMULAÇÃO)
# ==========================================
# Usado quando api_config = 'mock' no Excel

MOCK_DATA_CONFIG = {
    'variation': 0.5,  # Variação aleatória nos valores
    'base_values': {
        'temperature': 22.0,   # °C
        'humidity': 50.0,      # %
        'co2': 600,            # ppm
    }
}


# ==========================================
# DEFAULTS
# ==========================================
# Configurações padrão caso api_config não seja especificado

DEFAULT_HTTP_CONFIG = 'ncd_api'
DEFAULT_MQTT_CONFIG = 'mosquitto_local'  # Para futura implementação


# ==========================================
# CACHE E PERFORMANCE
# ==========================================

# Duração do cache em segundos (evita requests demasiado frequentes)
CACHE_DURATION = 30  # 30 segundos

# Timeout para conexões
CONNECTION_TIMEOUT = 10  # segundos


# ==========================================
# THRESHOLDS DE ALERTA
# ==========================================
# Limites para cada tipo de sensor

ALERT_THRESHOLDS = {
    'temperature': {
        'min': 18.0,           # °C
        'max': 26.0,           # °C
        'optimal_min': 20.0,
        'optimal_max': 24.0
    },
    'humidity': {
        'min': 30.0,           # %
        'max': 70.0,           # %
        'optimal_min': 40.0,
        'optimal_max': 60.0
    },
    'co2': {
        'max': 1000,           # ppm
        'warning': 800,
        'optimal_max': 600
    },
    'noise': {
        'max': 55,             # dB
        'optimal_max': 40
    }
}


# ==========================================
# LOGGING
# ==========================================

LOGGING_CONFIG = {
    'enabled': True,
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
    'file': 'ifc_iot_sensors.log',
    'max_size_mb': 10
}


# ==========================================
# EXEMPLOS DE USO NO EXCEL
# ==========================================
"""
ESTRUTURA DO EXCEL (excel_config_sens.xlsx):

| sensor_id      | ifc_global_id           | sensor_type  | api_config    | notes              |
|----------------|-------------------------|--------------|---------------|--------------------|
| TEMP_Q1_001    | 2X8uhRbQLEbg7HeUEPIuia | temperature  | ncd_api       | Sensor NCD         |
| HUM_Q1_001     | 2X8uhRbQLEbg7HeUEPIuia | humidity     | ncd_api       | Sensor NCD         |
| TEMP_Q2_002    | 1W7tgQaPKDbf6GdTDOHtgZ | temperature  | local_gateway | Gateway local      |
| CO2_SALA_001   | 3Y9viScRMFch8IfVFQJvjb | co2          | mock          | Dados simulados    |

COMO FUNCIONA:
1. Backend lê coluna 'api_config' do Excel
2. Busca configuração correspondente em HTTP_CONFIGS ou MQTT_CONFIGS
3. Usa essa configuração para ler dados do sensor
4. Se api_config = 'mock', gera dados simulados

VANTAGENS:
✅ Flexibilidade máxima: cada sensor pode usar API/protocolo diferente
✅ Sem hardcoding: configurações centralizadas aqui
✅ Fácil manutenção: trocar broker/API só altera este ficheiro
✅ Testes: sensores mock misturados com reais
✅ Preparado para MQTT quando necessário (implementação futura ~2-3 dias)
"""


# ==========================================
# BACKWARD COMPATIBILITY
# ==========================================
# Para compatibilidade com código antigo que usa SENSOR_TYPE único

SENSOR_TYPE = 'MOCK'  # Usado se api_config não for especificado


# ==========================================
# FUNÇÃO AUXILIAR: GET_SENSOR_CONFIG
# ==========================================

def get_sensor_config(api_config_name):
    """
    Obtém configuração de sensor baseado no nome do api_config
    
    Args:
        api_config_name: Nome da config (ex: 'ncd_api', 'mosquitto_local', 'mock')
    
    Returns:
        tuple: (protocol, config_dict)
        
    Examples:        
        >>> protocol, config = get_sensor_config('ncd_api')
        >>> print(protocol)  # 'HTTP'
        >>> print(config['base_url'])  # 'https://api.ncd.io/v1'
        
        >>> protocol, config = get_sensor_config('mosquitto_local')
        >>> print(protocol)  # 'MQTT'
        >>> print(config['broker'])  # 'localhost'
    """
    if not api_config_name:
        # Sem api_config especificado: usar default
        return 'MOCK', MOCK_DATA_CONFIG
    
    if api_config_name in HTTP_CONFIGS:
        return 'HTTP', HTTP_CONFIGS[api_config_name]
    
    elif api_config_name in MQTT_CONFIGS:
        # ⚠️ MQTT preparado mas não implementado
        # Se código tentar usar, falhará graciosamente
        return 'MQTT', MQTT_CONFIGS[api_config_name]
    
    elif api_config_name == 'mock':
        return 'MOCK', MOCK_DATA_CONFIG
    
    else:
        # Config desconhecido: usar default mock
        print(f"⚠️  Config '{api_config_name}' não encontrado, usando MOCK")
        return 'MOCK', MOCK_DATA_CONFIG


# ==========================================
# NOTAS FINAIS
# ==========================================
"""
CONFIGURAÇÃO INICIAL:

1. Editar HTTP_CONFIGS com as tuas APIs reais
2. Preencher excel_config_sens.xlsx com api_config apropriado
3. Testar com sensores mock primeiro
4. Gradualmente substituir mock por apis reais

PARA IMPLEMENTAR MQTT (FUTURAMENTE):

1. Instalar dependência:
   pip install paho-mqtt --break-system-packages

2. Criar subscriber em ifc_iot_server.py (~50-80 linhas):
   ```python
   import paho.mqtt.client as mqtt
   
   def on_connect(client, userdata, flags, rc):
       print(f"MQTT Connected: {rc}")
       client.subscribe("building/#")
   
   def on_message(client, userdata, msg):
       # Processar mensagem
       payload = json.loads(msg.payload)
       # Inserir em sensor_readings
   
   mqtt_client = mqtt.Client()
   mqtt_client.on_connect = on_connect
   mqtt_client.on_message = on_message
   mqtt_client.connect("localhost", 1883, 60)
   mqtt_client.loop_start()
   ```

3. Iniciar broker Mosquitto:
   docker run -p 1883:1883 eclipse-mosquitto

TROUBLESHOOTING:

Se sensores não funcionam:
1. Verificar se api_config no Excel está correto
2. Verificar se configuração existe neste ficheiro
3. Verificar conectividade (ping ao broker/API)
4. Verificar credenciais (api_key, username, password)
5. Ver logs em ifc_iot_sensors.log

SEGURANÇA:

⚠️  IMPORTANTE: Não commitar API keys para repositórios públicos!
- Usar variáveis de ambiente: os.environ.get('NCD_API_KEY')
- Ou ficheiro .env separado (adicionar ao .gitignore)
"""
