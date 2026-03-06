"""
SCRIPT DE IMPORTAÇÃO CORRIGIDO - DADOS MOHAMED STUDY
Caminho corrigido: data_Mohamed (onde os ficheiros estão)
"""

import pandas as pd
import requests
import os
from datetime import datetime
from tqdm import tqdm
import time

# ============================================
# CONFIGURAÇÃO CORRIGIDA
# ============================================

BACKEND_URL = "http://localhost:5000"
IFC_FILENAME = "Apartamentos_Validacao_VIVIENDA.ifc"
DATA_DIR = "data_Mohamed"  # ← CORRIGIDO! Era "data/mohamed_study"

# Mapeamento: Ficheiro Excel → Sensor ID + Tipo + GlobalId
SENSOR_MAPPING = {
    "api_measurement_BedroomR-Temp.xlsx": {
        "sensor_id": "BedroomR-Temp",
        "sensor_type": "temperature",
        "ifc_global_id": "BEDROOM-R-001",
        "space_name": "Quarto Renovado"
    },
    "api_measurement_BedroomR-RH.xlsx": {
        "sensor_id": "BedroomR-RH",
        "sensor_type": "humidity",
        "ifc_global_id": "BEDROOM-R-001",
        "space_name": "Quarto Renovado"
    },
    "api_measurement_BedroomNR-Temp.xlsx": {
        "sensor_id": "BedroomNR-Temp",
        "sensor_type": "temperature",
        "ifc_global_id": "BEDROOM-NR-002",
        "space_name": "Quarto Nao-Renovado"
    },
    "api_measurement_BedroomNR-RH.xlsx": {
        "sensor_id": "BedroomNR-RH",
        "sensor_type": "humidity",
        "ifc_global_id": "BEDROOM-NR-002",
        "space_name": "Quarto Nao-Renovado"
    },
    "api_measurement_LivingroomR-Temp.xlsx": {
        "sensor_id": "LivingroomR-Temp",
        "sensor_type": "temperature",
        "ifc_global_id": "LIVINGROOM-R-003",
        "space_name": "Sala Renovada"
    },
    "api_measurement_LivingroomR-RH.xlsx": {
        "sensor_id": "LivingroomR-RH",
        "sensor_type": "humidity",
        "ifc_global_id": "LIVINGROOM-R-003",
        "space_name": "Sala Renovada"
    },
    "api_measurement_LivingroomNR-Temp.xlsx": {
        "sensor_id": "LivingroomNR-Temp",
        "sensor_type": "temperature",
        "ifc_global_id": "LIVINGROOM-NR-004",
        "space_name": "Sala Nao-Renovada"
    },
    "api_measurement_LivingroomNR-RH.xlsx": {
        "sensor_id": "LivingroomNR-RH",
        "sensor_type": "humidity",
        "ifc_global_id": "LIVINGROOM-NR-004",
        "space_name": "Sala Nao-Renovada"
    }
}

# ============================================
# FUNÇÕES (mantêm-se iguais)
# ============================================

def check_backend():
    """Verifica se backend está online"""
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend online!")
            return True
        else:
            print(f"⚠️ Backend respondeu com status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Backend offline! Inicia o backend primeiro:")
        print("   python backend_v2_2_historico.py")
        return False
    except Exception as e:
        print(f"❌ Erro ao contactar backend: {e}")
        return False


def import_sensor_data(filename, sensor_info, batch_size=1000):
    """Importa dados de um sensor para o sistema"""
    
    filepath = os.path.join(DATA_DIR, filename)
    
    # Verificação melhorada
    if not os.path.exists(filepath):
        print(f"\n❌ Ficheiro não encontrado: {filepath}")
        print(f"   Caminho absoluto: {os.path.abspath(filepath)}")
        return 0
    
    print(f"\n📂 A processar: {filename}")
    print(f"   Caminho: {os.path.abspath(filepath)}")
    
    # Ler Excel
    try:
        df = pd.read_excel(filepath)
        print(f"   ✅ Lido: {len(df):,} registos")
    except Exception as e:
        print(f"   ❌ Erro ao ler ficheiro: {e}")
        return 0
    
    # Preparar leituras
    readings = []
    for _, row in df.iterrows():
        readings.append({
            "sensor_id": sensor_info["sensor_id"],
            "sensor_type": sensor_info["sensor_type"],
            "value": float(row['processed']),
            "unit": "°C" if sensor_info["sensor_type"] == "temperature" else "%",
            "timestamp": row['date_node'].isoformat(),
            "source": "mohamed_study",
            "space_name": sensor_info["space_name"]
        })
    
    # Enviar em batches
    total_batches = (len(readings) + batch_size - 1) // batch_size
    imported = 0
    errors = 0
    
    print(f"   Envio em {total_batches} batches de {batch_size} registos...")
    
    for i in tqdm(range(0, len(readings), batch_size), desc="   Importando"):
        batch = readings[i:i+batch_size]
        
        try:
            payload = {
                "ifc_filename": IFC_FILENAME,
                "readings": batch
            }
            
            response = requests.post(
                f"{BACKEND_URL}/api/sensors/ingest",
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                imported += len(batch)
            else:
                errors += len(batch)
                print(f"\n   ⚠️ Batch {i//batch_size} falhou: {response.status_code}")
        
        except Exception as e:
            errors += len(batch)
            print(f"\n   ❌ Erro no batch {i//batch_size}: {e}")
        
        time.sleep(0.1)
    
    print(f"   ✅ Importados: {imported:,} registos")
    if errors > 0:
        print(f"   ⚠️ Erros: {errors:,} registos")
    
    return imported


def main():
    print("=" * 70)
    print("IMPORTAÇÃO DE DADOS - ESTUDO MOHAMED ET AL. (2017)")
    print("=" * 70)
    print(f"\nBackend: {BACKEND_URL}")
    print(f"Modelo IFC: {IFC_FILENAME}")
    print(f"Diretório dados: {DATA_DIR}")
    print(f"Caminho absoluto: {os.path.abspath(DATA_DIR)}")
    print(f"Sensores a importar: {len(SENSOR_MAPPING)}")
    
    # Verificar se diretório existe
    if not os.path.exists(DATA_DIR):
        print(f"\n❌ ERRO: Diretório não encontrado!")
        print(f"   {os.path.abspath(DATA_DIR)}")
        print("\n💡 Cria o diretório ou corrige DATA_DIR no script")
        return
    
    # Listar ficheiros disponíveis
    print(f"\nFicheiros Excel no diretório:")
    excel_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.xlsx')]
    if excel_files:
        for f in excel_files:
            print(f"   ✅ {f}")
    else:
        print("   ❌ Nenhum ficheiro .xlsx encontrado!")
        return
    
    # 1. Verificar backend
    if not check_backend():
        return
    
    # 2. Importar dados de cada sensor
    print("\n" + "=" * 70)
    print("IMPORTAÇÃO DE DADOS")
    print("=" * 70)
    
    total_imported = 0
    start_time = time.time()
    
    for filename, sensor_info in SENSOR_MAPPING.items():
        imported = import_sensor_data(filename, sensor_info)
        total_imported += imported
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("RESUMO DA IMPORTAÇÃO")
    print("=" * 70)
    print(f"✅ Total importado: {total_imported:,} registos")
    print(f"⏱️ Tempo decorrido: {elapsed:.1f} segundos")
    if elapsed > 0:
        print(f"📊 Taxa: {total_imported/elapsed:.0f} registos/segundo")
    
    print("\n" + "=" * 70)
    print("✅ IMPORTAÇÃO CONCLUÍDA!")
    print("=" * 70)


if __name__ == "__main__":
    main()
