# -*- coding: utf-8 -*-
"""
BACKEND v2.2 - COM HISTÓRICO TEMPORAL
======================================
Nova funcionalidade: Guarda histórico de leituras e análise temporal
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import os
import sqlite3
from datetime import datetime, timedelta
import random
import json
import pandas as pd
from pathlib import Path

try:
    import ifcopenshell
    IFCOPENSHELL_AVAILABLE = True
except ImportError:
    IFCOPENSHELL_AVAILABLE = False

# ==========================================
# CONFIGURAÇÃO
# ==========================================

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "associations.db"
UPLOAD_DIR = DATA_DIR / "uploads"

# Criar diretórios se não existirem
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

MCP_DB_PATH = os.path.join(DATA_DIR, 'associations.db')

IFC_SPACES_CACHE = {}
CURRENT_IFC_FILE = None

# ==========================================
# DATABASE - HISTÓRICO TEMPORAL
# ==========================================

def init_database():
    """
    Inicializa BD com DUAS tabelas principais:
    1. associations - Associações sensor-espaço
    2. sensor_readings - Histórico de leituras

    Nota: O campo api_config na tabela associations é apenas metadados
    de texto (ex: "vesta_piso2"). O backend NÃO importa sensor_config.py
    nem realiza pedidos HTTP/MQTT automáticos. A ingestão de leituras
    reais é feita através do endpoint POST /api/sensors/ingest.
    A integração HTTP polling e MQTT está preparada arquiteturalmente
    em sensor_config.py para implementação futura.
    """
    if not os.path.exists(MCP_DB_PATH):
        print(f"📁 Criando nova base de dados: {MCP_DB_PATH}")
    
    conn = sqlite3.connect(MCP_DB_PATH)
    cursor = conn.cursor()
    
    # Tabela de associações (já existia)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ifc_filename TEXT NOT NULL,
            ifc_global_id TEXT NOT NULL,
            sensor_id TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            notes TEXT,
            api_config TEXT,  -- identificador do protocolo de recolha (ex: 'ncd_api', 'mosquitto_local'); referencia sensor_config.py para ingestão real futura
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ifc_filename, ifc_global_id, sensor_id)
        )
    """)




    # ✨ NOVA TABELA: Histórico de associações (mudanças)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS association_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ifc_filename TEXT NOT NULL,
            ifc_global_id TEXT NOT NULL,
            sensor_id TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)
    
    # ✨ NOVA TABELA: Histórico de leituras
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ifc_filename TEXT NOT NULL,
            ifc_global_id TEXT NOT NULL,
            space_name TEXT NOT NULL,
            sensor_id TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            source TEXT,
            timestamp TIMESTAMP NOT NULL,
            FOREIGN KEY (sensor_id) REFERENCES associations(sensor_id)
        )
    """)
    
    # Índices para queries temporais rápidas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_ifc_timestamp 
        ON sensor_readings(ifc_filename, timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_sensor_timestamp 
        ON sensor_readings(sensor_id, timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_space_timestamp 
        ON sensor_readings(ifc_filename, space_name, timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_associations_ifc 
        ON associations(ifc_filename)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_association_history_ifc 
        ON association_history(ifc_filename, timestamp DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_association_history_sensor 
        ON association_history(sensor_id, timestamp DESC)
    """)
    
    conn.commit()
    conn.close()
    print("✅ Base de dados v2.2 inicializada (com histórico temporal)")

# ==========================================
# FUNÇÕES HISTÓRICO
# ==========================================

def save_sensor_readings(readings_list):
    """
    Guarda lista de leituras de sensores na BD
    
    readings_list = [{
        'ifc_filename': 'edificio.ifc',
        'ifc_global_id': '2O2Fr$...',
        'space_name': 'Sala 1',
        'sensor_id': 'TEMP_01',
        'sensor_type': 'temperature',
        'value': 22.5,
        'unit': '°C',
        'source': 'MOCK_AUTO',
        'timestamp': '2025-01-15T10:30:00'
    }, ...]
    """
    if not readings_list:
        return {'success': False, 'error': 'Nenhuma leitura fornecida'}
    
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        for reading in readings_list:
            cursor.execute("""
                INSERT INTO sensor_readings 
                (ifc_filename, ifc_global_id, space_name, sensor_id, sensor_type, 
                 value, unit, source, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reading['ifc_filename'],
                reading['ifc_global_id'],
                reading['space_name'],
                reading['sensor_id'],
                reading['sensor_type'],
                reading['value'],
                reading.get('unit', ''),
                reading.get('source', 'UNKNOWN'),
                reading.get('timestamp', datetime.now().isoformat())
            ))
        
        conn.commit()
        conn.close()
        
        print(f"💾 {len(readings_list)} leituras guardadas")
        return {
            'success': True,
            'saved': len(readings_list),
            'message': f'{len(readings_list)} leituras guardadas'
        }
        
    except Exception as e:
        print(f"❌ Erro ao guardar leituras: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_readings_history(ifc_filename, sensor_type=None, space_name=None, 
                         start_date=None, end_date=None, limit=1000):
    """
    Obtém histórico de leituras com filtros
    """
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Construir query dinamicamente
        query = "SELECT * FROM sensor_readings WHERE ifc_filename = ?"
        params = [ifc_filename]
        
        if sensor_type:
            query += " AND sensor_type = ?"
            params.append(sensor_type)
        
        if space_name:
            query += " AND space_name = ?"
            params.append(space_name)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        readings = []
        for row in cursor.fetchall():
            readings.append({
                'id': row['id'],
                'ifc_filename': row['ifc_filename'],
                'space_name': row['space_name'],
                'sensor_id': row['sensor_id'],
                'sensor_type': row['sensor_type'],
                'value': row['value'],
                'unit': row['unit'],
                'source': row['source'],
                'timestamp': row['timestamp']
            })
        
        conn.close()
        
        print(f"📊 {len(readings)} leituras obtidas do histórico")
        return readings
        
    except Exception as e:
        print(f"❌ Erro ao obter histórico: {str(e)}")
        return []


def get_temporal_statistics(ifc_filename, sensor_type, aggregation='daily', 
                            start_date=None, end_date=None):
    """
    Calcula estatísticas temporais (agregações por hora/dia/mês)
    
    aggregation: 'hourly', 'daily', 'monthly'
    """
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Definir formato de agrupamento
        if aggregation == 'hourly':
            time_format = '%Y-%m-%d %H:00:00'
        elif aggregation == 'daily':
            time_format = '%Y-%m-%d'
        elif aggregation == 'monthly':
            time_format = '%Y-%m'
        else:
            time_format = '%Y-%m-%d'
        
        query = f"""
            SELECT 
                strftime('{time_format}', timestamp) as period,
                space_name,
                COUNT(*) as count,
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                STDEV(value) as std_dev
            FROM sensor_readings
            WHERE ifc_filename = ? AND sensor_type = ?
        """
        
        params = [ifc_filename, sensor_type]
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        query += " GROUP BY period, space_name ORDER BY period DESC"
        
        cursor.execute(query, params)
        
        stats = []
        for row in cursor.fetchall():
            stats.append({
                'period': row[0],
                'space_name': row[1],
                'count': row[2],
                'avg': round(row[3], 2) if row[3] else None,
                'min': round(row[4], 2) if row[4] else None,
                'max': round(row[5], 2) if row[5] else None,
                'std_dev': round(row[6], 2) if row[6] else None
            })
        
        conn.close()
        
        print(f"📈 Estatísticas calculadas: {len(stats)} períodos")
        return stats
        
    except Exception as e:
        print(f"❌ Erro nas estatísticas: {str(e)}")
        return []


def analyze_monthly_thermal_comfort(ifc_filename, year, month):
    """
    Análise de conforto térmico mensal
    Baseado em ISO 7730 (20-24°C confortável)
    """
    try:
        # Datas do mês
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year+1}-01-01"
        else:
            end_date = f"{year}-{month+1:02d}-01"
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Query para análise mensal
        cursor.execute("""
            SELECT 
                space_name,
                COUNT(*) as total_readings,
                AVG(value) as avg_temp,
                MIN(value) as min_temp,
                MAX(value) as max_temp,
                SUM(CASE WHEN value < 20 THEN 1 ELSE 0 END) as cold_count,
                SUM(CASE WHEN value >= 20 AND value <= 24 THEN 1 ELSE 0 END) as comfort_count,
                SUM(CASE WHEN value > 24 THEN 1 ELSE 0 END) as warm_count
            FROM sensor_readings
            WHERE ifc_filename = ? 
              AND sensor_type = 'temperature'
              AND timestamp >= ? 
              AND timestamp < ?
            GROUP BY space_name
        """, (ifc_filename, start_date, end_date))
        
        analysis = []
        for row in cursor.fetchall():
            total = row[1]
            comfort_pct = (row[6] / total * 100) if total > 0 else 0
            cold_pct = (row[5] / total * 100) if total > 0 else 0
            warm_pct = (row[7] / total * 100) if total > 0 else 0
            
            # Classificação
            if comfort_pct >= 90:
                classification = 'Excelente'
            elif comfort_pct >= 70:
                classification = 'Bom'
            elif comfort_pct >= 50:
                classification = 'Aceitável'
            else:
                classification = 'Problemático'
            
            analysis.append({
                'space_name': row[0],
                'total_readings': total,
                'avg_temp': round(row[2], 2),
                'min_temp': round(row[3], 2),
                'max_temp': round(row[4], 2),
                'comfort_percentage': round(comfort_pct, 1),
                'cold_percentage': round(cold_pct, 1),
                'warm_percentage': round(warm_pct, 1),
                'classification': classification
            })
        
        conn.close()
        
        print(f"🔍 Análise mensal: {len(analysis)} espaços")
        return {
            'month': f"{year}-{month:02d}",
            'spaces': analysis,
            'summary': {
                'total_spaces': len(analysis),
                'excellent_spaces': sum(1 for s in analysis if s['classification'] == 'Excelente'),
                'good_spaces': sum(1 for s in analysis if s['classification'] == 'Bom'),
                'problematic_spaces': sum(1 for s in analysis if s['classification'] == 'Problemático')
            }
        }
        
    except Exception as e:
        print(f"❌ Erro na análise mensal: {str(e)}")
        return {'error': str(e)}


# ==========================================
# FUNÇÕES GESTÃO DE ASSOCIAÇÕES
# ==========================================

def log_association_action(ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes=''):
    """
    Regista ação de associação no histórico
    action: 'created', 'modified', 'deleted'
    """
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO association_history 
            (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes))
        
        conn.commit()
        conn.close()
        
        print(f"📝 Histórico: {action} - {sensor_id} → {ifc_global_id}")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao registar histórico: {str(e)}")
        return False


def create_association(ifc_filename, ifc_global_id, sensor_id, sensor_type, notes=''):
    """Cria nova associação sensor-espaço"""
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO associations 
            (ifc_filename, ifc_global_id, sensor_id, sensor_type, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (ifc_filename, ifc_global_id, sensor_id, sensor_type, notes))
        
        conn.commit()
        conn.close()
        
        # Registar no histórico
        log_association_action(ifc_filename, ifc_global_id, sensor_id, sensor_type, 'created', notes)
        
        print(f"✅ Associação criada: {sensor_id} → {ifc_global_id}")
        return {'success': True, 'message': 'Associação criada'}
        
    except sqlite3.IntegrityError:
        return {'success': False, 'error': 'Associação já existe'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_associations(ifc_filename=None):
    """Lista todas as associações (opcionalmente filtradas por ficheiro)"""
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ifc_filename:
            cursor.execute("""
                SELECT * FROM associations 
                WHERE ifc_filename = ?
                ORDER BY created_at DESC
            """, (ifc_filename,))
        else:
            cursor.execute("SELECT * FROM associations ORDER BY created_at DESC")
        
        associations = []
        for row in cursor.fetchall():
            associations.append({
                'id': row['id'],
                'ifc_filename': row['ifc_filename'],
                'ifc_global_id': row['ifc_global_id'],
                'sensor_id': row['sensor_id'],
                'sensor_type': row['sensor_type'],
                'notes': row['notes'],
                'created_at': row['created_at']
            })
        
        conn.close()
        
        print(f"📋 {len(associations)} associações listadas")
        return associations
        
    except Exception as e:
        print(f"❌ Erro ao listar associações: {str(e)}")
        return []


def delete_association(association_id):
    """Apaga associação e regista no histórico"""
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Obter dados antes de apagar (para histórico)
        cursor.execute("SELECT * FROM associations WHERE id = ?", (association_id,))
        row = cursor.fetchone()
        
        if not row:
            return {'success': False, 'error': 'Associação não encontrada'}
        
        ifc_filename, ifc_global_id, sensor_id, sensor_type = row[1], row[2], row[3], row[4]
        
        # Apagar associação
        cursor.execute("DELETE FROM associations WHERE id = ?", (association_id,))
        conn.commit()
        conn.close()
        
        # Registar no histórico
        log_association_action(ifc_filename, ifc_global_id, sensor_id, sensor_type, 'deleted')
        
        print(f"🗑️ Associação apagada: ID {association_id}")
        return {'success': True, 'message': 'Associação apagada'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_association_history(ifc_filename=None, limit=100):
    """Obtém histórico de mudanças nas associações"""
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ifc_filename:
            cursor.execute("""
                SELECT * FROM association_history 
                WHERE ifc_filename = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (ifc_filename, limit))
        else:
            cursor.execute("""
                SELECT * FROM association_history 
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                'id': row['id'],
                'ifc_filename': row['ifc_filename'],
                'ifc_global_id': row['ifc_global_id'],
                'sensor_id': row['sensor_id'],
                'sensor_type': row['sensor_type'],
                'action': row['action'],
                'timestamp': row['timestamp'],
                'notes': row['notes']
            })
        
        conn.close()
        
        print(f"📜 {len(history)} entradas de histórico")
        return history
        
    except Exception as e:
        print(f"❌ Erro ao obter histórico: {str(e)}")
        return []


# ==========================================
# FUNÇÕES IFC (mantidas da v2.1)
# ==========================================

def get_ifc_spaces_from_file(filename):
    """Extrai espaços (igual v2.1)"""
    global IFC_SPACES_CACHE, CURRENT_IFC_FILE
    
    if filename in IFC_SPACES_CACHE:
        CURRENT_IFC_FILE = filename
        return IFC_SPACES_CACHE[filename]
    
    if not IFCOPENSHELL_AVAILABLE:
        raise Exception("ifcopenshell não instalado")
    
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        raise Exception(f"Ficheiro não encontrado: {filename}")
    
    try:
        ifc_file = ifcopenshell.open(filepath)
        spaces = ifc_file.by_type('IfcSpace')
        
        spaces_list = []
        for space in spaces:
            space_info = {
                'global_id': space.GlobalId,
                'name': space.Name or f"Space_{space.GlobalId[:8]}",
                'long_name': getattr(space, 'LongName', None),
                'description': getattr(space, 'Description', None),
                'object_type': getattr(space, 'ObjectType', None)
            }
            spaces_list.append(space_info)
        
        IFC_SPACES_CACHE[filename] = spaces_list
        CURRENT_IFC_FILE = filename
        
        print(f"✅ {len(spaces_list)} espaços extraídos: {filename}")
        return spaces_list
        
    except Exception as e:
        raise


def get_mcp_associations(ifc_filename=None):
    """Lê associações (igual v2.1)"""
    if not os.path.exists(MCP_DB_PATH):
        return []
    
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ifc_filename:
            cursor.execute("""
                SELECT * FROM associations
                WHERE ifc_filename = ?
                ORDER BY created_at DESC
            """, (ifc_filename,))
        else:
            cursor.execute("SELECT * FROM associations ORDER BY created_at DESC")
        
        associations = []
        for row in cursor.fetchall():
            associations.append({
                'id': row['id'],
                'ifc_filename': row['ifc_filename'],
                'ifc_global_id': row['ifc_global_id'],
                'sensor_id': row['sensor_id'],
                'sensor_type': row['sensor_type'],
                'notes': row['notes'],
                'created_at': row['created_at']
            })
        
        conn.close()
        return associations
        
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
        return []


def generate_mock_sensor_data(ifc_filename):
    """Gera MOCK e GUARDA no histórico"""
    spaces = IFC_SPACES_CACHE.get(ifc_filename, [])
    if not spaces:
        return []
    
    mock_data = []
    base_values = {'temperature': 22.0, 'humidity': 50.0, 'co2': 650}
    
    for space in spaces:
        space_name = space.get('name') or f"Space_{space['global_id'][:8]}"
        
        # Temperatura
        temp = round(base_values['temperature'] + random.uniform(-2, 2), 2)
        mock_data.append({
            'sensor_id': f"mock_temp_{space['global_id'][:8]}",
            'space_name': space_name,
            'ifc_global_id': space['global_id'],
            'ifc_filename': ifc_filename,
            'sensor_type': 'temperature',
            'value': temp,
            'unit': '°C',
            'timestamp': datetime.now().isoformat(),
            'status': 'online',
            'source': 'MOCK_AUTO'
        })
        
        # Humidade
        hum = round(base_values['humidity'] + random.uniform(-10, 10), 2)
        mock_data.append({
            'sensor_id': f"mock_hum_{space['global_id'][:8]}",
            'space_name': space_name,
            'ifc_global_id': space['global_id'],
            'ifc_filename': ifc_filename,
            'sensor_type': 'humidity',
            'value': hum,
            'unit': '%',
            'timestamp': datetime.now().isoformat(),
            'status': 'online',
            'source': 'MOCK_AUTO'
        })
        
        # CO2
        co2 = int(base_values['co2'] + random.uniform(-150, 150))
        mock_data.append({
            'sensor_id': f"mock_co2_{space['global_id'][:8]}",
            'space_name': space_name,
            'ifc_global_id': space['global_id'],
            'ifc_filename': ifc_filename,
            'sensor_type': 'co2',
            'value': co2,
            'unit': 'ppm',
            'timestamp': datetime.now().isoformat(),
            'status': 'online',
            'source': 'MOCK_AUTO'
        })
    
    # ✨ GUARDAR no histórico
    save_sensor_readings(mock_data)
    
    return mock_data


def get_all_sensor_data(ifc_filename):
    """
    Devolve dados de sensores para o ficheiro IFC indicado.

    Comportamento:
    - Se existirem leituras geradas há menos de MOCK_INTERVAL_SECONDS,
      devolve as mais recentes da BD (evita crescimento descontrolado).
    - Caso contrário, gera novo mock e guarda no histórico,
      mantendo séries temporais realistas para análise evolutiva.

    Em produção, substituir pela leitura de sensores reais via HTTP/MQTT.
    """
    MOCK_INTERVAL_SECONDS = 300  # 5 minutos entre gerações automáticas

    if not ifc_filename:
        return []

    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()

        row = cursor.execute("""
            SELECT MAX(timestamp) FROM sensor_readings
            WHERE ifc_filename = ?
        """, (ifc_filename,)).fetchone()
        conn.close()

        last_ts = row[0] if row else None

        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)
                age_seconds = (datetime.now() - last_dt).total_seconds()
                if age_seconds < MOCK_INTERVAL_SECONDS:
                    return _get_latest_readings_from_db(ifc_filename)
            except ValueError:
                pass

    except Exception:
        pass

    return generate_mock_sensor_data(ifc_filename)


def _get_latest_readings_from_db(ifc_filename):
    """
    Devolve a leitura mais recente de cada sensor_id para o ficheiro IFC,
    no mesmo formato de generate_mock_sensor_data.
    """
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        rows = cursor.execute("""
            SELECT sensor_id, space_name, ifc_global_id, ifc_filename,
                   sensor_type, value, unit, timestamp, source
            FROM sensor_readings
            WHERE ifc_filename = ?
              AND timestamp = (
                  SELECT MAX(s2.timestamp)
                  FROM sensor_readings s2
                  WHERE s2.ifc_filename = sensor_readings.ifc_filename
                    AND s2.sensor_id    = sensor_readings.sensor_id
              )
        """, (ifc_filename,)).fetchall()
        conn.close()

        return [dict(r) for r in rows]

    except Exception:
        return []


# ==========================================
# ENDPOINTS - HISTÓRICO TEMPORAL
# ==========================================

@app.route('/api/history/readings')
def get_readings_history_endpoint():
    """
    Obtém histórico de leituras
    Parâmetros: file, sensor_type, space_name, start_date, end_date, limit
    """
    ifc_filename = request.args.get('file')
    if not ifc_filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    
    try:
        sensor_type = request.args.get('sensor_type')
        space_name = request.args.get('space_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 1000))
        
        readings = get_readings_history(
            ifc_filename, sensor_type, space_name,
            start_date, end_date, limit
        )
        
        return jsonify({
            'success': True,
            'count': len(readings),
            'readings': readings,
            'filters': {
                'file': ifc_filename,
                'sensor_type': sensor_type,
                'space_name': space_name,
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history/statistics')
def get_statistics_endpoint():
    """
    Estatísticas temporais agregadas
    Parâmetros: file, sensor_type, aggregation, start_date, end_date
    """
    ifc_filename = request.args.get('file')
    sensor_type = request.args.get('sensor_type', 'temperature')
    
    if not ifc_filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    
    try:
        aggregation = request.args.get('aggregation', 'daily')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        stats = get_temporal_statistics(
            ifc_filename, sensor_type, aggregation,
            start_date, end_date
        )
        
        return jsonify({
            'success': True,
            'count': len(stats),
            'statistics': stats,
            'aggregation': aggregation,
            'sensor_type': sensor_type
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/monthly')
def get_monthly_analysis_endpoint():
    """
    Análise de conforto térmico mensal
    Parâmetros: file, year, month
    """
    ifc_filename = request.args.get('file')
    
    if not ifc_filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    
    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
        
        analysis = analyze_monthly_thermal_comfort(ifc_filename, year, month)
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# ENDPOINT - ESTATÍSTICAS POR ESPAÇO (HISTÓRICO COMPLETO)
# ==========================================

@app.route('/api/history/space-stats')
def get_space_statistics():
    ifc_filename = request.args.get('file')
    sensor_type_filter = request.args.get('sensor_type')
    if not ifc_filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    try:
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        query = """
            SELECT space_name, sensor_type, COUNT(*) AS n,
                ROUND(AVG(value),4) AS mean,
                ROUND(MIN(value),4) AS min_val,
                ROUND(MAX(value),4) AS max_val,
                ROUND(SQRT(AVG(value*value)-AVG(value)*AVG(value)),4) AS std_dev,
                ROUND(100.0*SUM(CASE
                    WHEN sensor_type='temperature' AND value>=20 AND value<=26 THEN 1
                    WHEN sensor_type='humidity' AND value>=40 AND value<=60 THEN 1
                    ELSE 0 END)/COUNT(*),1) AS iso7730_compliance_pct,
                MIN(timestamp) AS first_reading, MAX(timestamp) AS last_reading
            FROM sensor_readings WHERE ifc_filename=?
        """
        params = [ifc_filename]
        if sensor_type_filter:
            query += " AND sensor_type=?"
            params.append(sensor_type_filter)
        query += " GROUP BY space_name, sensor_type ORDER BY space_name, sensor_type"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return jsonify({'success': False, 'error': f'Sem dados para {ifc_filename}'}), 404
        season_query = """
            SELECT space_name, sensor_type,
                CASE WHEN CAST(strftime('%m',timestamp) AS INTEGER) IN (12,1,2) THEN 'inverno'
                     WHEN CAST(strftime('%m',timestamp) AS INTEGER) IN (3,4,5)  THEN 'primavera'
                     WHEN CAST(strftime('%m',timestamp) AS INTEGER) IN (6,7,8)  THEN 'verao'
                     ELSE 'outono' END AS season,
                COUNT(*) AS n, ROUND(AVG(value),2) AS mean,
                ROUND(100.0*SUM(CASE
                    WHEN sensor_type='temperature' AND value>=20 AND value<=26 THEN 1
                    WHEN sensor_type='humidity' AND value>=40 AND value<=60 THEN 1
                    ELSE 0 END)/COUNT(*),1) AS compliance_pct
            FROM sensor_readings WHERE ifc_filename=?
        """
        season_params = [ifc_filename]
        if sensor_type_filter:
            season_query += " AND sensor_type=?"
            season_params.append(sensor_type_filter)
        season_query += " GROUP BY space_name, sensor_type, season ORDER BY space_name, sensor_type, season"
        cursor.execute(season_query, season_params)
        season_rows = cursor.fetchall()
        conn.close()
        spaces = {}
        for r in rows:
            sn, st, n, mean, mn, mx, sd, comp, first, last = r
            if sn not in spaces:
                spaces[sn] = {"space_name": sn, "sensors": {}}
            spaces[sn]["sensors"][st] = {"n": n, "mean": mean, "min": mn, "max": mx,
                "std_dev": sd, "iso7730_compliance_pct": comp,
                "first_reading": first, "last_reading": last, "seasonal": {}}
        for r in season_rows:
            sn, st, season, n, mean, comp = r
            if sn in spaces and st in spaces[sn]["sensors"]:
                spaces[sn]["sensors"][st]["seasonal"][season] = {"n": n, "mean": mean, "compliance_pct": comp}
        return jsonify({'success': True, 'ifc_filename': ifc_filename,
            'total_spaces': len(spaces), 'iso_standard': 'ISO 7730 (T: 20-26°C, HR: 40-60%)',
            'spaces': list(spaces.values())})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# ENDPOINTS - GESTÃO DE ASSOCIAÇÕES
# ==========================================

@app.route('/api/ifc/associate', methods=['POST'])
def associate_sensor():
    """
    Cria associação sensor-espaço
    Body JSON: {
        "ifc_filename": "edificio.ifc",
        "ifc_global_id": "2O2Fr$...",
        "sensor_id": "TEMP_01",
        "sensor_type": "temperature",
        "notes": "opcional"
    }
    """
    try:
        data = request.get_json()
        
        required = ['ifc_filename', 'ifc_global_id', 'sensor_id', 'sensor_type']
        if not all(k in data for k in required):
            return jsonify({
                'success': False,
                'error': f'Campos obrigatórios: {required}'
            }), 400
        
        result = create_association(
            data['ifc_filename'],
            data['ifc_global_id'],
            data['sensor_id'],
            data['sensor_type'],
            data.get('notes', '')
        )
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/ifc/associations', methods=['GET'])
def get_associations():
    """
    ✓ ROTA ADICIONADA - Listar todas as associações sensor-espaço
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Permite acesso por nome de coluna
        cursor = conn.cursor()
        
        # Buscar todas as associações
        cursor.execute('''
            SELECT 
                id,
                ifc_filename,
                ifc_global_id,
                sensor_id,
                sensor_type,
                notes,
                created_at,
            FROM associations
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        # Converter para lista de dicionários
        associations = []
        for row in rows:
            associations.append({
                "id": row["id"],
                "ifc_filename": row["ifc_filename"],
                "ifc_global_id": row["ifc_global_id"],
                "sensor_id": row["sensor_id"],
                "sensor_type": row["sensor_type"],
                "notes": row["notes"] or "",
                "created_at": row["created_at"],
            })
        
        return jsonify({
            "total": len(associations),
            "associations": associations
        }), 200
    
    except Exception as e:
        return jsonify({
            "error": f"Erro ao buscar associações: {str(e)}"
        }), 500

@app.route('/api/associations')
def list_associations():
    """
    Lista todas as associações
    Parâmetro opcional: file (ifc_filename)
    """
    try:
        ifc_filename = request.args.get('file')
        associations = get_associations(ifc_filename)
        
        return jsonify({
            'success': True,
            'count': len(associations),
            'associations': associations,
            'file': ifc_filename
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/<int:association_id>', methods=['DELETE'])
def delete_association_endpoint(association_id):
    """Apaga associação por ID"""
    try:
        result = delete_association(association_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/history')
def get_associations_history_endpoint():
    """
    Obtém histórico de mudanças nas associações
    Parâmetros: file (opcional), limit (opcional, default 100)
    """
    try:
        ifc_filename = request.args.get('file')
        limit = int(request.args.get('limit', 100))
        
        history = get_association_history(ifc_filename, limit)
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history,
            'file': ifc_filename
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# ENDPOINTS EXISTENTES (v2.1)
# ==========================================

@app.route('/')
def index():
    """Info do sistema"""
    return jsonify({
        'service': 'BIM + IoT Digital Twin Backend',
        'version': '2.2 - Histórico Temporal',
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'features': [
            'Múltiplos projetos IFC',
            'Histórico de leituras',
            'Análise temporal',
            'Estatísticas agregadas',
            'Análise mensal de conforto'
        ]
    })


@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy'})


@app.route('/api/sensors/current')
def get_current_sensors():
    """Dados atuais (e guarda no histórico)"""
    ifc_filename = request.args.get('file')
    if not ifc_filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    
    try:
        sensor_data = get_all_sensor_data(ifc_filename)
        
        grouped = {}
        for s in sensor_data:
            space = s.get("space_name")
            if not space:
                continue
            
            if space not in grouped:
                grouped[space] = {
                    "space_name": space,
                    "ifc_global_id": s.get("ifc_global_id"),
                    "source": s.get("source")
                }
            
            grouped[space][s["sensor_type"]] = s["value"]
        
        mode = "REAL" if sensor_data and sensor_data[0].get('source') == 'MCP_REAL' else "MOCK"
        
        return jsonify({
            "success": True,
            "spaces": list(grouped.values()),
            "count": len(grouped),
            "mode": mode,
            "ifc_filename": ifc_filename,
            "timestamp": datetime.now().isoformat(),
            "saved_to_history": True  # ✨ NOVO
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/ifc/upload', methods=['POST'])
def upload_ifc():
    """Upload IFC"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Nenhum ficheiro'}), 400
        
        file = request.files['file']
        if not file.filename.lower().endswith('.ifc'):
            return jsonify({'success': False, 'error': 'Apenas .ifc'}), 400
        
        filepath = os.path.join(DATA_DIR, file.filename)
        file.save(filepath)
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'message': 'Upload concluído'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ifc/spaces')
def get_ifc_spaces():
    """Extrai espaços"""
    filename = request.args.get('file')
    if not filename:
        return jsonify({'success': False, 'error': 'Parâmetro "file" obrigatório'}), 400
    
    try:
        spaces = get_ifc_spaces_from_file(filename)
        return jsonify({
            'success': True,
            'count': len(spaces),
            'spaces': spaces,
            'file': filename
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# ⭐ NOVAS FUNÇÕES MCP - GESTÃO AVANÇADA
# ==========================================
# Adicionar imports no TOPO do ficheiro se não existirem:
#   import pandas as pd
#   from flask import send_file

@app.route('/api/associations/disassociate', methods=['POST'])
def disassociate_sensor():
    """
    Remove associação de um sensor específico
    
    Body JSON:
        {
            "sensor_id": "TEMP_Q1_001"
        }
    """
    try:
        data = request.get_json()
        sensor_id = data.get('sensor_id')
        
        if not sensor_id:
            return jsonify({
                'success': False,
                'error': 'sensor_id é obrigatório'
            }), 400
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Obter informação antes de apagar
        cursor.execute("""
            SELECT sensor_id, ifc_global_id, sensor_type, notes, ifc_filename
            FROM associations
            WHERE sensor_id = ?
        """, (sensor_id,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Sensor {sensor_id} não encontrado'
            }), 404
        
        # Registar no histórico
        cursor.execute("""
            INSERT INTO association_history 
            (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes)
            VALUES (?, ?, ?, ?, 'REMOVED', ?)
        """, (result[4], result[1], result[0], result[2], f'Sensor desassociado via API'))
        
        # Apagar associação
        cursor.execute("DELETE FROM associations WHERE sensor_id = ?", (sensor_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Sensor {sensor_id} desassociado com sucesso',
            'removed': {
                'sensor_id': result[0],
                'ifc_global_id': result[1],
                'sensor_type': result[2],
                'notes': result[3]
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/disassociate_space', methods=['POST'])
def disassociate_space():
    """
    Remove todos os sensores associados a um espaço
    
    Body JSON:
        {
            "ifc_filename": "edificio.ifc",
            "ifc_global_id": "2X8uhRbQLEbg7HeUEPIuia"
        }
    """
    try:
        data = request.get_json()
        ifc_filename = data.get('ifc_filename')
        ifc_global_id = data.get('ifc_global_id')
        
        if not ifc_filename or not ifc_global_id:
            return jsonify({
                'success': False,
                'error': 'ifc_filename e ifc_global_id são obrigatórios'
            }), 400
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Obter lista de sensores antes de apagar
        cursor.execute("""
            SELECT sensor_id, sensor_type
            FROM associations
            WHERE ifc_filename = ? AND ifc_global_id = ?
        """, (ifc_filename, ifc_global_id))
        
        sensors = cursor.fetchall()
        
        if not sensors:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Nenhum sensor encontrado para o espaço'
            }), 404
        
        # Registar no histórico
        for sensor in sensors:
            cursor.execute("""
                INSERT INTO association_history 
                (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes)
                VALUES (?, ?, ?, ?, 'REMOVED', ?)
            """, (ifc_filename, ifc_global_id, sensor[0], sensor[1], 'Espaço desassociado via API'))
        
        # Apagar todas as associações deste espaço
        cursor.execute("""
            DELETE FROM associations 
            WHERE ifc_filename = ? AND ifc_global_id = ?
        """, (ifc_filename, ifc_global_id))
        
        conn.commit()
        conn.close()
        
        sensor_list = [{'sensor_id': s[0], 'sensor_type': s[1]} for s in sensors]
        
        return jsonify({
            'success': True,
            'message': f'{len(sensors)} sensores removidos do espaço',
            'removed_sensors': sensor_list,
            'count': len(sensors)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/reset', methods=['POST'])
def reset_all_associations():
    """
    Remove TODAS as associações da base de dados
    ⚠️ OPERAÇÃO IRREVERSÍVEL - usar com cuidado!
    
    Body JSON:
        {
            "confirm": true
        }
    """
    try:
        data = request.get_json()
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmação necessária. Envie {"confirm": true}'
            }), 400
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Contar associações antes de apagar
        cursor.execute("SELECT COUNT(*) as count FROM associations")
        count = cursor.fetchone()[0]
        
        # Registar no histórico
        cursor.execute("""
            INSERT INTO association_history 
            (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes)
            SELECT ifc_filename, ifc_global_id, sensor_id, sensor_type, 'RESET', 'Reset total via API'
            FROM associations
        """)
        
        # Apagar tudo
        cursor.execute("DELETE FROM associations")
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Todas as {count} associações foram removidas',
            'count': count,
            'warning': 'Operação irreversível completada'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/update', methods=['POST'])
def update_association():
    """
    Atualiza associação existente (ex: mover sensor para outro espaço)
    
    Body JSON:
        {
            "sensor_id": "TEMP_Q1_001",
            "ifc_filename": "edificio.ifc",
            "new_ifc_global_id": "3Y9viScRMFch8IfVFQJvjb",
            "new_notes": "Movido para Sala",
            "new_api_config": "vesta_piso2"  # opcional
        }
    """
    try:
        data = request.get_json()
        sensor_id = data.get('sensor_id')
        ifc_filename = data.get('ifc_filename')
        new_ifc_global_id = data.get('new_ifc_global_id')
        new_notes = data.get('new_notes', '')
        new_api_config = data.get('new_api_config', '')
        
        if not sensor_id or not ifc_filename or not new_ifc_global_id:
            return jsonify({
                'success': False,
                'error': 'sensor_id, ifc_filename e new_ifc_global_id são obrigatórios'
            }), 400
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Verificar se sensor existe
        cursor.execute("""
            SELECT ifc_global_id, sensor_type FROM associations 
            WHERE sensor_id = ? AND ifc_filename = ?
        """, (sensor_id, ifc_filename))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Sensor {sensor_id} não encontrado'
            }), 404
        
        old_ifc_global_id = result[0]
        sensor_type = result[1]
        
        # Registar no histórico
        cursor.execute("""
            INSERT INTO association_history 
            (ifc_filename, ifc_global_id, sensor_id, sensor_type, action, notes)
            VALUES (?, ?, ?, ?, 'UPDATED', ?)
        """, (ifc_filename, new_ifc_global_id, sensor_id, sensor_type, 
              f'Movido de {old_ifc_global_id[:8]}... para {new_ifc_global_id[:8]}...'))
        
        # Atualizar associação
        cursor.execute("""
            UPDATE associations
            SET ifc_global_id = ?, 
                notes = ?,
                api_config = ?,
                created_at = CURRENT_TIMESTAMP
            WHERE sensor_id = ? AND ifc_filename = ?
        """, (new_ifc_global_id, new_notes, new_api_config, sensor_id, ifc_filename))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Sensor {sensor_id} atualizado com sucesso',
            'old_ifc_global_id': old_ifc_global_id,
            'new_ifc_global_id': new_ifc_global_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/bulk_from_excel', methods=['POST'])
def bulk_associate_from_excel():
    """
    Carrega associações em massa de ficheiro Excel
    
    Body JSON:
        {
            "ifc_filename": "edificio.ifc",
            "excel_path": "/path/to/excel_config_sens.xlsx",
            "mode": "merge"  # ou "replace" ou "append"
        }
    
    Formato Excel:
        | sensor_id | ifc_global_id | sensor_type | api_config | notes |
    """
    try:
        # Verificar se pandas está instalado
        try:
            import pandas as pd
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'pandas não instalado. Execute: pip install pandas openpyxl'
            }), 500
        
        data = request.get_json()
        ifc_filename = data.get('ifc_filename')
        excel_path = data.get('excel_path')
        mode = data.get('mode', 'merge')
        
        if not ifc_filename or not excel_path:
            return jsonify({
                'success': False,
                'error': 'ifc_filename e excel_path são obrigatórios'
            }), 400
        
        if mode not in ['replace', 'merge', 'append']:
            return jsonify({
                'success': False,
                'error': 'mode deve ser: replace, merge ou append'
            }), 400
        
        # Ler Excel
        try:
            df = pd.read_excel(excel_path)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Erro ao ler Excel: {str(e)}'
            }), 400
        
        # Validar colunas
        required_cols = ['sensor_id', 'ifc_global_id', 'sensor_type']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            return jsonify({
                'success': False,
                'error': f'Colunas em falta no Excel: {missing_cols}'
            }), 400
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Modo REPLACE: apagar associações antigas deste ficheiro
        if mode == 'replace':
            cursor.execute("DELETE FROM associations WHERE ifc_filename = ?", (ifc_filename,))
        
        added = []
        updated = []
        errors = []
        
        # Processar cada linha do Excel
        for index, row in df.iterrows():
            try:
                sensor_id = str(row['sensor_id']).strip()
                ifc_global_id = str(row['ifc_global_id']).strip()
                sensor_type = str(row['sensor_type']).strip()
                api_config = str(row.get('api_config', '')).strip() if 'api_config' in row else ''
                notes = str(row.get('notes', '')).strip() if 'notes' in row else ''
                
                # Verificar se já existe
                cursor.execute("""
                    SELECT id FROM associations 
                    WHERE ifc_filename = ? AND sensor_id = ? AND sensor_type = ?
                """, (ifc_filename, sensor_id, sensor_type))
                
                exists = cursor.fetchone()
                
                if exists and mode == 'append':
                    # Modo append: sempre adicionar (pode criar duplicados)
                    cursor.execute("""
                        INSERT INTO associations 
                        (ifc_filename, ifc_global_id, sensor_id, sensor_type, api_config, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (ifc_filename, ifc_global_id, sensor_id, sensor_type, api_config, notes))
                    added.append(sensor_id)
                
                elif exists and mode == 'merge':
                    # Modo merge: atualizar existente
                    cursor.execute("""
                        UPDATE associations
                        SET ifc_global_id = ?, api_config = ?, notes = ?
                        WHERE ifc_filename = ? AND sensor_id = ? AND sensor_type = ?
                    """, (ifc_global_id, api_config, notes, ifc_filename, sensor_id, sensor_type))
                    updated.append(sensor_id)
                
                else:
                    # Não existe: inserir novo
                    cursor.execute("""
                        INSERT INTO associations 
                        (ifc_filename, ifc_global_id, sensor_id, sensor_type, api_config, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (ifc_filename, ifc_global_id, sensor_id, sensor_type, api_config, notes))
                    added.append(sensor_id)
                
            except Exception as e:
                errors.append(f"Linha {index+2}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'{len(added)} sensores adicionados, {len(updated)} atualizados',
            'added': added,
            'updated': updated,
            'errors': errors,
            'mode': mode
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/export_excel')
def export_associations_excel():
    """
    Exporta todas as associações para ficheiro Excel
    Parâmetro opcional: file (ifc_filename)
    """
    try:
        # Verificar se pandas está instalado
        try:
            import pandas as pd
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'pandas não instalado. Execute: pip install pandas openpyxl'
            }), 500
        
        ifc_filename = request.args.get('file')
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        # Obter associações
        if ifc_filename:
            cursor.execute("""
                SELECT sensor_id, ifc_global_id, sensor_type, api_config, notes, created_at
                FROM associations
                WHERE ifc_filename = ?
                ORDER BY created_at DESC
            """, (ifc_filename,))
        else:
            cursor.execute("""
                SELECT sensor_id, ifc_global_id, sensor_type, api_config, notes, created_at
                FROM associations
                ORDER BY created_at DESC
            """)
        
        data = cursor.fetchall()
        conn.close()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Nenhuma associação encontrada para exportar'
            }), 404
        
        # Converter para DataFrame
        df = pd.DataFrame(data, columns=[
            'sensor_id', 'ifc_global_id', 'sensor_type', 
            'api_config', 'notes', 'created_at'
        ])
        
        # Gerar nome do ficheiro
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'associations_backup_{timestamp}.xlsx'
        filepath = os.path.join(DATA_DIR, filename)
        
        # Guardar Excel
        df.to_excel(filepath, index=False, sheet_name='Associations')
        
        # Enviar ficheiro
        return send_file(
            filepath,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/associations/stats')
def get_association_stats():
    """
    Estatísticas sobre associações
    Parâmetro opcional: file (ifc_filename)
    """
    try:
        ifc_filename = request.args.get('file')
        
        conn = sqlite3.connect(MCP_DB_PATH)
        cursor = conn.cursor()
        
        where_clause = "WHERE ifc_filename = ?" if ifc_filename else ""
        params = (ifc_filename,) if ifc_filename else ()
        
        # Total de associações
        cursor.execute(f"SELECT COUNT(*) FROM associations {where_clause}", params)
        total_assoc = cursor.fetchone()[0]
        
        # Total de sensores únicos
        cursor.execute(f"SELECT COUNT(DISTINCT sensor_id) FROM associations {where_clause}", params)
        total_sensors = cursor.fetchone()[0]
        
        # Total de espaços com sensores
        cursor.execute(f"SELECT COUNT(DISTINCT ifc_global_id) FROM associations {where_clause}", params)
        total_spaces = cursor.fetchone()[0]
        
        # Por tipo de sensor
        cursor.execute(f"""
            SELECT sensor_type, COUNT(*) as count
            FROM associations {where_clause}
            GROUP BY sensor_type
        """, params)
        by_type = dict(cursor.fetchall())
        
        # Por configuração API
        cursor.execute(f"""
            SELECT api_config, COUNT(*) as count
            FROM associations 
            {where_clause}
            {"AND" if where_clause else "WHERE"} api_config IS NOT NULL AND api_config != ''
            GROUP BY api_config
        """, params)
        by_api = dict(cursor.fetchall())
        
        conn.close()
        
        avg_sensors = round(total_assoc / total_spaces, 1) if total_spaces > 0 else 0
        
        return jsonify({
            'success': True,
            'total_associations': total_assoc,
            'total_spaces': total_spaces,
            'total_sensors': total_sensors,
            'by_sensor_type': by_type,
            'by_api_config': by_api,
            'sensors_per_space_avg': avg_sensors,
            'file': ifc_filename
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# FIM DAS NOVAS FUNÇÕES
# ==========================================

# ==========================================
# INICIALIZAÇÃO
# ==========================================
 
# Inicializar BD ao arrancar
init_database()

print("=" * 60)
print(" Backend v2.2 – HISTÓRICO TEMPORAL")
print("=" * 60)
print(f" Base de dados: {DB_PATH}")
print(f" Servidor: http://localhost:5000")
print("=" * 60)

# -*- coding: utf-8 -*-
"""
EXTENSÃO HTTP PARA BACKEND v2.2
================================
Adicionar ao backend_v2_2_historico.py

Este código adiciona suporte para ingestão de dados de sensores via HTTP
(ideal para tese - simples, testável, demonstrável)
"""

# ==========================================
# ADICIONAR ESTE CÓDIGO AO backend_v2_2_historico.py
# ==========================================

"""
INSTRUÇÕES:
1. Copiar este código para o final do backend_v2_2_historico.py (antes do if __name__)
2. Testar com curl ou Postman
3. Demonstrar na defesa
"""

# ==========================================
# ENDPOINT DE INGESTÃO HTTP
# ==========================================

@app.route('/api/sensors/ingest', methods=['POST'])
def ingest_sensor_data():
    """
    ⭐ ENDPOINT PRINCIPAL PARA RECEBER DADOS DE SENSORES VIA HTTP
    
    Este endpoint permite que qualquer dispositivo IoT (ESP32, Arduino, 
    Raspberry Pi, gateway comercial) envie dados via HTTP POST.
    
    PROTOCOLO:
    ----------
    POST /api/sensors/ingest
    Content-Type: application/json
    
    Body JSON (Formato Simples):
    {
        "ifc_filename": "edificio.ifc",
        "sensor_id": "TEMP_Q1_001",
        "sensor_type": "temperature",
        "value": 22.5,
        "unit": "°C",
        "space_name": "Sala 1",               # OPCIONAL
        "ifc_global_id": "2O2Fr$t4X7Zf...",   # OPCIONAL
        "timestamp": "2025-01-15T10:30:00"    # OPCIONAL (usa now() se omitido)
    }
    
    Body JSON (Formato Batch - Múltiplos Sensores):
    {
        "ifc_filename": "edificio.ifc",
        "readings": [
            {
                "sensor_id": "TEMP_Q1_001",
                "sensor_type": "temperature",
                "value": 22.5,
                "unit": "°C"
            },
            {
                "sensor_id": "HUM_Q1_001",
                "sensor_type": "humidity",
                "value": 50.0,
                "unit": "%"
            }
        ]
    }
    
    EXEMPLOS DE USO:
    ----------------
    
    # 1. ESP32/Arduino (C++)
    HTTPClient http;
    http.begin("http://192.168.1.100:5000/api/sensors/ingest");
    http.addHeader("Content-Type", "application/json");
    String payload = "{\"ifc_filename\":\"edificio.ifc\",\"sensor_id\":\"TEMP_01\",\"sensor_type\":\"temperature\",\"value\":22.5}";
    int httpCode = http.POST(payload);
    
    # 2. Python (Sensor Script)
    import requests
    data = {
        "ifc_filename": "edificio.ifc",
        "sensor_id": "TEMP_Q1_001",
        "sensor_type": "temperature",
        "value": 22.5,
        "unit": "°C"
    }
    response = requests.post("http://localhost:5000/api/sensors/ingest", json=data)
    
    # 3. curl (Teste Manual)
    curl -X POST http://localhost:5000/api/sensors/ingest \
      -H "Content-Type: application/json" \
      -d '{"ifc_filename":"edificio.ifc","sensor_id":"TEMP_01","sensor_type":"temperature","value":22.5}'
    
    # 4. JavaScript (Node.js)
    fetch('http://localhost:5000/api/sensors/ingest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ifc_filename: 'edificio.ifc',
            sensor_id: 'TEMP_01',
            sensor_type: 'temperature',
            value: 22.5
        })
    });
    
    RESPOSTAS:
    ----------
    Success (200):
    {
        "success": true,
        "message": "1 leitura(s) guardada(s) com sucesso",
        "saved": 1,
        "readings": [{...}]
    }
    
    Error (400):
    {
        "success": false,
        "error": "Campos obrigatórios: ifc_filename, sensor_id, sensor_type, value"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Body JSON vazio ou inválido'
            }), 400
        
        # ============================================
        # MODO 1: Leitura Única (Formato Simples)
        # ============================================
        if 'sensor_id' in data:
            # Validar campos obrigatórios
            required = ['ifc_filename', 'sensor_id', 'sensor_type', 'value']
            missing = [field for field in required if field not in data]
            
            if missing:
                return jsonify({
                    'success': False,
                    'error': f'Campos obrigatórios em falta: {missing}'
                }), 400
            
            # Verificar se sensor está associado (buscar espaço)
            conn = sqlite3.connect(MCP_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT ifc_global_id FROM associations
                WHERE ifc_filename = ? AND sensor_id = ?
            """, (data['ifc_filename'], data['sensor_id']))
            
            association = cursor.fetchone()
            conn.close()
            
            # Se não associado, criar associação automática
            if not association:
                print(f"⚠️ Sensor {data['sensor_id']} não associado - criando associação automática")
                
                # Usar ifc_global_id fornecido ou criar genérico
                ifc_global_id = data.get('ifc_global_id', f"AUTO_{data['sensor_id']}")
                
                create_association(
                    data['ifc_filename'],
                    ifc_global_id,
                    data['sensor_id'],
                    data['sensor_type'],
                    notes='Associação automática via HTTP ingest'
                )
            else:
                ifc_global_id = association['ifc_global_id']
            
            # Criar leitura
            reading = {
                'ifc_filename': data['ifc_filename'],
                'ifc_global_id': ifc_global_id,
                'space_name': data.get('space_name', f"Space_{data['sensor_id'][:8]}"),
                'sensor_id': data['sensor_id'],
                'sensor_type': data['sensor_type'],
                'value': float(data['value']),
                'unit': data.get('unit', ''),
                'source': data.get('source', 'HTTP_INGEST'),
                'timestamp': data.get('timestamp', datetime.now().isoformat())
            }
            
            result = save_sensor_readings([reading])
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': '1 leitura guardada com sucesso',
                    'saved': 1,
                    'readings': [reading]
                }), 200
            else:
                return jsonify(result), 500
        
        # ============================================
        # MODO 2: Batch (Múltiplas Leituras)
        # ============================================
        elif 'readings' in data:
            if not data.get('ifc_filename'):
                return jsonify({
                    'success': False,
                    'error': 'Campo ifc_filename obrigatório para batch'
                }), 400
            
            readings_list = []
            
            for idx, r in enumerate(data['readings']):
                # Validar campos obrigatórios
                required = ['sensor_id', 'sensor_type', 'value']
                missing = [field for field in required if field not in r]
                
                if missing:
                    return jsonify({
                        'success': False,
                        'error': f'Leitura {idx}: campos em falta: {missing}'
                    }), 400
                
                # Buscar associação
                conn = sqlite3.connect(MCP_DB_PATH)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT ifc_global_id FROM associations
                    WHERE ifc_filename = ? AND sensor_id = ?
                """, (data['ifc_filename'], r['sensor_id']))
                
                association = cursor.fetchone()
                conn.close()
                
                # Auto-associar se necessário
                if not association:
                    ifc_global_id = r.get('ifc_global_id', f"AUTO_{r['sensor_id']}")
                    create_association(
                        data['ifc_filename'],
                        ifc_global_id,
                        r['sensor_id'],
                        r['sensor_type'],
                        notes='Auto-associação batch HTTP'
                    )
                else:
                    ifc_global_id = association['ifc_global_id']
                
                # Criar leitura
                reading = {
                    'ifc_filename': data['ifc_filename'],
                    'ifc_global_id': ifc_global_id,
                    'space_name': r.get('space_name', f"Space_{r['sensor_id'][:8]}"),
                    'sensor_id': r['sensor_id'],
                    'sensor_type': r['sensor_type'],
                    'value': float(r['value']),
                    'unit': r.get('unit', ''),
                    'source': r.get('source', 'HTTP_INGEST_BATCH'),
                    'timestamp': r.get('timestamp', datetime.now().isoformat())
                }
                
                readings_list.append(reading)
            
            result = save_sensor_readings(readings_list)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': f"{len(readings_list)} leituras guardadas com sucesso",
                    'saved': len(readings_list),
                    'readings': readings_list
                }), 200
            else:
                return jsonify(result), 500
        
        else:
            return jsonify({
                'success': False,
                'error': 'Body deve conter "sensor_id" (simples) ou "readings" (batch)'
            }), 400
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Valor inválido: {str(e)}'
        }), 400
    
    except Exception as e:
        print(f"❌ Erro na ingestão HTTP: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/sensors/test', methods=['GET'])
def test_sensor_ingest():
    """
    Endpoint de teste - Simula envio de sensor HTTP
    
    GET /api/sensors/test?file=edificio.ifc
    
    Gera automaticamente uma leitura de teste e envia para /api/sensors/ingest
    """
    ifc_filename = request.args.get('file', 'test.ifc')
    
    # Gerar leitura de teste
    test_reading = {
        'ifc_filename': ifc_filename,
        'sensor_id': f'TEST_TEMP_{datetime.now().strftime("%H%M%S")}',
        'sensor_type': 'temperature',
        'value': round(20 + random.uniform(-5, 5), 2),
        'unit': '°C',
        'space_name': 'Test Space',
        'source': 'HTTP_TEST'
    }
    
    # Enviar para endpoint de ingestão
    with app.test_client() as client:
        response = client.post(
            '/api/sensors/ingest',
            json=test_reading,
            content_type='application/json'
        )
        result = response.get_json()
    
    return jsonify({
        'success': True,
        'message': 'Teste de ingestão HTTP executado',
        'test_reading': test_reading,
        'ingest_result': result
    }), 200


@app.route('/api/sensors/simulate', methods=['POST'])
def simulate_continuous_sensors():
    """
    Simula sensores enviando dados continuamente via HTTP
    
    POST /api/sensors/simulate
    Body: {
        "ifc_filename": "edificio.ifc",
        "num_sensors": 5,
        "interval_seconds": 60,
        "duration_minutes": 10
    }
    
    Útil para:
    - Testar sistema sob carga
    - Gerar histórico de dados
    - Demonstração em tempo real
    """
    try:
        data = request.get_json()
        
        ifc_filename = data.get('ifc_filename', 'simulation.ifc')
        num_sensors = data.get('num_sensors', 5)
        
        # Gerar leituras simuladas
        readings = []
        base_temp = 22.0
        
        for i in range(num_sensors):
            sensor_id = f'SIM_TEMP_{i+1:03d}'
            
            reading = {
                'ifc_filename': ifc_filename,
                'sensor_id': sensor_id,
                'sensor_type': 'temperature',
                'value': round(base_temp + random.uniform(-3, 3), 2),
                'unit': '°C',
                'space_name': f'Simulated Space {i+1}',
                'ifc_global_id': f'SIM_{i+1:03d}',
                'source': 'HTTP_SIMULATION'
            }
            
            readings.append(reading)
        
        # Guardar todas as leituras
        result = save_sensor_readings(readings)
        
        return jsonify({
            'success': True,
            'message': f'{num_sensors} sensores simulados criados',
            'sensors': readings,
            'result': result
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==========================================
# ESTATÍSTICAS DE INGESTÃO
# ==========================================

@app.route('/api/sensors/ingest/stats')
def get_ingest_stats():
    """
    Estatísticas sobre dados recebidos via HTTP ingest
    
    GET /api/sensors/ingest/stats?file=edificio.ifc
    
    Retorna:
    - Total de leituras HTTP
    - Leituras por sensor
    - Última leitura de cada sensor
    - Taxa de ingestão (leituras/hora)
    """
    try:
        ifc_filename = request.args.get('file')
        
        conn = sqlite3.connect(MCP_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Total de leituras HTTP
        query = """
            SELECT COUNT(*) as total
            FROM sensor_readings
            WHERE source LIKE 'HTTP%'
        """
        params = []
        
        if ifc_filename:
            query += " AND ifc_filename = ?"
            params.append(ifc_filename)
        
        cursor.execute(query, params)
        total = cursor.fetchone()['total']
        
        # Por sensor
        query = """
            SELECT 
                sensor_id,
                sensor_type,
                COUNT(*) as count,
                AVG(value) as avg_value,
                MAX(timestamp) as last_reading
            FROM sensor_readings
            WHERE source LIKE 'HTTP%'
        """
        
        if ifc_filename:
            query += " AND ifc_filename = ?"
        
        query += " GROUP BY sensor_id ORDER BY count DESC"
        
        cursor.execute(query, params)
        by_sensor = []
        
        for row in cursor.fetchall():
            by_sensor.append({
                'sensor_id': row['sensor_id'],
                'sensor_type': row['sensor_type'],
                'count': row['count'],
                'avg_value': round(row['avg_value'], 2) if row['avg_value'] else None,
                'last_reading': row['last_reading']
            })
        
        # Taxa de ingestão (última hora)
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        
        query = """
            SELECT COUNT(*) as count
            FROM sensor_readings
            WHERE source LIKE 'HTTP%'
              AND timestamp >= ?
        """
        params_rate = [one_hour_ago]
        
        if ifc_filename:
            query += " AND ifc_filename = ?"
            params_rate.append(ifc_filename)
        
        cursor.execute(query, params_rate)
        last_hour = cursor.fetchone()['count']
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_http_readings': total,
            'sensors': by_sensor,
            'num_sensors': len(by_sensor),
            'last_hour_readings': last_hour,
            'readings_per_hour': last_hour,
            'file': ifc_filename
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==========================================
# DOCUMENTAÇÃO API
# ==========================================

@app.route('/api/docs/http-ingest')
def docs_http_ingest():
    """
    Documentação completa do endpoint HTTP ingest
    """
    docs = {
        'title': 'API de Ingestão de Sensores HTTP',
        'version': '2.2',
        'description': 'Endpoint para receber dados de sensores IoT via HTTP POST',
        
        'endpoints': {
            '/api/sensors/ingest': {
                'method': 'POST',
                'description': 'Recebe dados de sensores (simples ou batch)',
                'body_format_simple': {
                    'ifc_filename': 'string (obrigatório)',
                    'sensor_id': 'string (obrigatório)',
                    'sensor_type': 'string (obrigatório)',
                    'value': 'number (obrigatório)',
                    'unit': 'string (opcional)',
                    'space_name': 'string (opcional)',
                    'timestamp': 'ISO8601 (opcional)'
                },
                'body_format_batch': {
                    'ifc_filename': 'string (obrigatório)',
                    'readings': 'array (obrigatório)'
                },
                'example_curl': 'curl -X POST http://localhost:5000/api/sensors/ingest -H "Content-Type: application/json" -d \'{"ifc_filename":"test.ifc","sensor_id":"TEMP_01","sensor_type":"temperature","value":22.5}\''
            },
            
            '/api/sensors/test': {
                'method': 'GET',
                'description': 'Gera e envia leitura de teste',
                'params': 'file=edificio.ifc (opcional)'
            },
            
            '/api/sensors/simulate': {
                'method': 'POST',
                'description': 'Simula múltiplos sensores',
                'body': {
                    'ifc_filename': 'string',
                    'num_sensors': 'int',
                    'interval_seconds': 'int',
                    'duration_minutes': 'int'
                }
            },
            
            '/api/sensors/ingest/stats': {
                'method': 'GET',
                'description': 'Estatísticas de ingestão HTTP',
                'params': 'file=edificio.ifc (opcional)'
            }
        },
        
        'supported_sensor_types': [
            'temperature', 'humidity', 'co2', 
        ],
        
        'integration_examples': {
            'ESP32': 'Ver código em docs/examples/esp32_http_sensor.ino',
            'Python': 'Ver código em docs/examples/python_http_sensor.py',
            'Node.js': 'Ver código em docs/examples/nodejs_http_sensor.js'
        }
    }
    
    return jsonify(docs), 200


# ==========================================
# FIM DA EXTENSÃO HTTP
# ==========================================

print("\n" + "="*60)
print(" 🌐 EXTENSÃO HTTP PARA SENSORES CARREGADA")
print("="*60)
print(" Novos endpoints:")
print("   POST /api/sensors/ingest         - Ingestão de dados")
print("   GET  /api/sensors/test           - Teste rápido")
print("   POST /api/sensors/simulate       - Simulação contínua")
print("   GET  /api/sensors/ingest/stats   - Estatísticas HTTP")
print("   GET  /api/docs/http-ingest       - Documentação")
print("="*60 + "\n")

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("🚀 BIM + IoT Backend v2.2 - HISTÓRICO TEMPORAL")
    print("=" * 80)
    print(f"📁 Diretório: {DATA_DIR}")
    print(f"🗄️ Base de dados: {MCP_DB_PATH}")
    print(f"🌐 Servidor: http://localhost:5000")
    print("=" * 80)
    print("\n✨ NOVIDADES v2.2:")
    print("  • Histórico de leituras de sensores")
    print("  • Histórico de associações sensor-espaço")
    print("  • Estatísticas temporais (hora/dia/mês)")
    print("  • Análise mensal de conforto térmico")
    print("  • Agregações e tendências")
    print("  • Gestão completa de associações")
    print("=" * 80)
    print("\nEndpoints - Associações:")
    print("  POST   /api/ifc/associate                  - Criar associação")
    print("  GET    /api/associations                   - Listar associações")
    print("  DELETE /api/associations/<id>              - Apagar associação")
    print("  GET    /api/associations/history           - Histórico de mudanças")
    print("\n  ⭐ NOVOS v2.3:")
    print("  POST   /api/associations/disassociate      - Remover sensor")
    print("  POST   /api/associations/disassociate_space- Remover espaço")
    print("  POST   /api/associations/update            - Mover sensor")
    print("  POST   /api/associations/reset             - Reset total (⚠️)")
    print("  POST   /api/associations/bulk_from_excel   - Carregar Excel")
    print("  GET    /api/associations/export_excel      - Exportar Excel")
    print("  GET    /api/associations/stats             - Estatísticas")
    print("\nEndpoints - Histórico Temporal:")
    print("  GET /api/history/readings           - Histórico de leituras")
    print("  GET /api/history/statistics         - Estatísticas agregadas")
    print("  GET /api/analysis/monthly           - Análise mensal")
    print("=" * 80)
    print("\nExemplos:")
    print("  POST /api/ifc/associate")
    print("       Body: {\"ifc_filename\":\"edificio.ifc\",\"ifc_global_id\":\"2O2Fr$...\",\"sensor_id\":\"TEMP_01\",\"sensor_type\":\"temperature\"}")
    print("  GET  /api/associations?file=edificio.ifc")
    print("  GET  /api/associations/history?file=edificio.ifc&limit=50")
    print("  GET  /api/history/readings?file=edificio.ifc&sensor_type=temperature&limit=100")
    print("  GET  /api/history/statistics?file=edificio.ifc&aggregation=daily")
    print("  GET  /api/analysis/monthly?file=edificio.ifc&year=2025&month=1")
    print("=" * 80)
    print("\nCTRL+C para parar\n")
    
    init_database()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
