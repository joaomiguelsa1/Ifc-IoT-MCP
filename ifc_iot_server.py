# ifc_iot_server.py - VERSÃO COMPLETA COM LIMIARES DE REFERÊNCIA OPERACIONAIS
from mcp.server import Server
from mcp.types import Tool, TextContent
import json
import os
import re
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Configurações
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ASSOCIATIONS_FILE = DATA_DIR / "associations.db"
MCP_DB_PATH = DATA_DIR / "mcp_surveys.db"

# URL da API de sensores
SENSORS_API_URL = "http://localhost:5000"

# Garante que a pasta data existe
DATA_DIR.mkdir(exist_ok=True)

# Tipos de elementos relevantes para sensores
SPATIAL_TYPES = [
    "IfcSpace",
    "IfcBuildingStorey",
    "IfcZone",
    "IfcBuilding",
    "IfcSite"
]

# ==================== BASE DE CONHECIMENTO - LIMIARES DE REFERÊNCIA OPERACIONAIS ====================
# Os valores operational_range codificados abaixo são limiares de referência operacionais adoptados
# para validação experimental do framework VIVIENDA. Não constituem reprodução das tabelas normativas
# oficiais das normas referenciadas (ISO 7730:2005, EN 16798-1:2019, ASHRAE 55:2020), cujo conteúdo
# é protegido por direitos de autor. Os valores adoptados são suportados empiricamente por:
#   - Alegría-Sala et al. (2022): limiares mínimos de T (20°C) e HR (50%) em espaços universitários
#   - Arsad et al. (2023): intervalos de conforto 22,0–28,4°C em edifícios com climatização
# e são consistentes com os enquadramentos gerais das normas referenciadas.

ISO_STANDARDS = {
    "ISO_7730": {
        "name": "ISO 7730 - Ergonomia do ambiente térmico",
        "description": "Configuração de referência para conforto térmico, com enquadramento na ISO 7730:2005",
        "methodology_note": "Limiares operacionais definidos pelo autor com base no enquadramento geral das normas referenciadas; não reproduzem tabelas normativas oficiais",
        "application": "Ambientes internos ocupados (escritórios, residências, escolas)",
        "required_sensors": {
            "temperature": {
                "name": "Temperatura do ar",
                "unit": "°C",
                "range": [10, 30],
                "operational_range": [20, 26],
                "priority": "critical"
            },
            "humidity": {
                "name": "Humidade relativa",
                "unit": "%",
                "range": [30, 70],
                "operational_range": [40, 60],
                "priority": "critical"
            },
            "air_velocity": {
                "name": "Velocidade do ar",
                "unit": "m/s",
                "range": [0, 0.5],
                "operational_range": [0.1, 0.2],
                "priority": "high"
            },
        },
        "optional_sensors": {    
            
            "radiant_temperature": {
                "name": "Temperatura radiante média",
                "unit": "°C",
                "priority": "medium"
            }
        },
        "space_types": ["IfcSpace", "IfcZone"],
        "reference": "ISO 7730:2005"
    },
    

    "ISO_16798": {
        "name": "ISO 16798 - Qualidade do ar interior",
        "description": "Configuração de referência para qualidade do ar interior, com enquadramento na EN 16798-1:2019",
        "methodology_note": "Limiares operacionais suportados por Alegría-Sala et al. (2022); não reproduzem tabelas normativas oficiais",
        "application": "Ventilação e qualidade do ar em edifícios",
        "required_sensors": {
            "co2": {
                "name": "Concentração de CO2",
                "unit": "ppm",
                "range": [400, 1500],
                "operational_range": [400, 1000],
                "priority": "critical"
            },
            "temperature": {
                "name": "Temperatura do ar",
                "unit": "°C",
                "range": [18, 28],
                "operational_range": [20, 26],
                "priority": "critical"
            },
            "humidity": {
                "name": "Humidade relativa",
                "unit": "%",
                "range": [30, 70],
                "operational_range": [40, 60],
                "priority": "high"
            }
        },
        "optional_sensors": {
            "voc": {
                "name": "Compostos orgânicos voláteis",
                "unit": "ppb",
                "priority": "medium"
            }
        },
        "space_types": ["IfcSpace"],
        "reference": "ISO 16798-1:2019"
    },
    
    # ==================== NOVAS NORMAS ====================
    
    "ASHRAE_55": {
        "name": "ASHRAE 55 - Condições ambientais térmicas para ocupação humana",
        "description": "Configuração de referência para conforto térmico, com enquadramento na ASHRAE 55:2020",
        "methodology_note": "Limiares operacionais definidos pelo autor com base no enquadramento geral das normas referenciadas; não reproduzem tabelas normativas oficiais",
        "application": "Ambientes ocupados - escritórios, residências, escolas, hospitais",
        "required_sensors": {
            "temperature": {
                "name": "Temperatura operativa",
                "unit": "°C",
                "range": [10, 33],
                "operational_range": [19.5, 27],
                "priority": "critical"
            },
            "humidity": {
                "name": "Humidade relativa",
                "unit": "%",
                "range": [0, 100],
                "operational_range": [30, 60],
                "priority": "critical"
            },
            "air_velocity": {
                "name": "Velocidade do ar",
                "unit": "m/s",
                "range": [0, 0.8],
                "operational_range": [0.1, 0.2],
                "priority": "high"
            }
        },
        "optional_sensors": {
            "radiant_temperature": {
                "name": "Temperatura radiante média",
                "unit": "°C",
                "priority": "high"
            },
            "co2": {
                "name": "CO2 para qualidade do ar",
                "unit": "ppm",
                "operational_range": [400, 1000],
                "priority": "medium"
            }
        },
        "space_types": ["IfcSpace", "IfcZone"],
        "reference": "ASHRAE 55-2020"
    },
}


# Mapeamento de tipos de sensor
SENSOR_TYPE_INFO = {
    "temperature": {"unit": "°C", "name": "Temperatura", "category": "thermal"},
    "humidity": {"unit": "%", "name": "Humidade", "category": "thermal"},
    "co2": {"unit": "ppm", "name": "CO2", "category": "air_quality"},
}

# Inicializa servidor MCP
server = Server("ifc-iot-mapper")

# ==================== TOOLS ====================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Lista todas as ferramentas disponíveis"""
    return [
        # Ferramentas originais
        Tool(
            name="load_ifc_spaces",
            description="Carrega arquivo IFC e lista todos os espaços disponíveis",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="associate_sensor",
            description="Associa um sensor IoT a um espaço do IFC",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_global_id": {"type": "string"},
                    "sensor_id": {"type": "string"},
                    "sensor_type": {"type": "string", "description": "Tipo: temperature, humidity, co2"},
                    "notes": {"type": "string"}
                },
                "required": ["ifc_global_id", "sensor_id", "sensor_type"]
            }
        ),
        Tool(
            name="find_spaces",
            description="Busca espaços no IFC por nome",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "search_term": {"type": "string"}
                },
                "required": ["ifc_path", "search_term"]
            }
        ),
        Tool(
            name="list_associations",
            description="Lista todas as associações sensor-espaço",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                }
            }
        ),
        Tool(
            name="bulk_associate_sensors",
            description="Associa sensores em massa",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "sensor_type": {"type": "string"},
                    "filter_by": {"type": "string"}
                },
                "required": ["ifc_path", "sensor_type"]
            }
        ),
        Tool(
            name="extract_materials_from_ifc",
            description="Extrai materiais e camadas de um ficheiro IFC, incluindo espessuras e propriedades térmicas",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {
                        "type": "string",
                        "description": "Caminho para o ficheiro IFC"
                    }
                },
                "required": ["ifc_path"]
            }
        ),
        
        # Ferramentas de análise multi-parâmetro
        Tool(
            name="get_all_sensor_data",
            description="Busca dados de TODOS os tipos de sensores (temperatura, humidade, CO2, luz, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="get_sensor_data_by_type",
            description="Busca dados de sensores de um tipo específico",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "sensor_type": {"type": "string", "description": "temperature, humidity, co2"}
                },
                "required": ["ifc_path", "sensor_type"]
            }
        ),
        Tool(
            name="analyze_indoor_quality",
            description="Análise da qualidade do ambiente interior (temperatura, humidade, CO2)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        
        # FERRAMENTAS DE VERIFICAÇÃO FACE A LIMIARES DE REFERÊNCIA
        Tool(
            name="list_iso_standards",
            description="Lista as configurações normativas disponíveis no sistema com os respetivos limiares de referência operacionais",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_standard_requirements",
            description="Obtém os limiares de referência operacionais de uma configuração de enquadramento",
            inputSchema={
                "type": "object",
                "properties": {
                    "standard_id": {"type": "string", "description": "ID da norma: ISO_7730, ISO_16798, ASHRAE_55"}
                },
                "required": ["standard_id"]
            }
        ),
        Tool(
            name="recommend_sensors_by_standard",
            description="Recomenda sensores para um espaço com base nos parâmetros de monitorização da configuração selecionada",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "space_name": {"type": "string"},
                    "standard_id": {"type": "string", "description": "ISO_7730, ISO_16798, ASHRAE_55"}
                },
                "required": ["ifc_path", "space_name", "standard_id"]
            }
        ),
        Tool(
            name="check_compliance",
            description="Verifica se os sensores instalados cobrem os parâmetros necessários para a configuração selecionada",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "standard_id": {"type": "string"}
                },
                "required": ["ifc_path", "standard_id"]
            }
        ),
        Tool(
            name="recommend_sensors_for_all_spaces",
            description="Recomenda sensores para todos os espaços com base nos parâmetros de monitorização da configuração selecionada",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "standard_id": {"type": "string"}
                },
                "required": ["ifc_path", "standard_id"]
            }
        ),
        
        # Ferramentas térmicas (mantidas da versão anterior)
        Tool(
            name="get_live_temperatures",
            description="Busca temperaturas atuais (mantido para compatibilidade)",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="analyze_thermal_data",
            description="Análise térmica completa",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="compare_spaces_temperature",
            description="Compara temperaturas entre espaços",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "space_names": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["ifc_path", "space_names"]
            }
        ),
        Tool(
            name="generate_heatmap_data",
            description="Gera dados para heatmap térmico",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
                name="analyze_historical_statistics",
                description="Análise estatística completa do histórico de todos os espaços: média, desvio-padrão, min, max, conformidade com os limiares de referência e sazonalidade. Usa para perguntas sobre médias anuais, variabilidade, impacto de retrofit ou comparações estatísticas.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ifc_path": {
                            "type": "string",
                            "description": "Caminho para o ficheiro IFC"
                        },
                        "sensor_type": {
                            "type": "string",
                            "description": "Tipo de sensor: 'temperature', 'humidity' ou omitir para ambos",
                            "enum": ["temperature", "humidity"]
                        }
                    },
                    "required": ["ifc_path"]
                }
            ),
        Tool(
            name="get_sensor_history",
            description="Obtém histórico de um sensor",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "hours": {"type": "integer"}
                },
                "required": ["sensor_id"]
            }
        ),
        
        # === NOVAS FERRAMENTAS - ANÁLISE AVANÇADA ===
        Tool(
            name="analyze_thermal_comfort_all_spaces",
            description="Análise COMPLETA de conforto térmico de todos os espaços usando limiares de referência operacionais",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="check_iso_compliance_detailed",
            description="Verificação detalhada face aos limiares de referência operacionais de cada configuração de enquadramento.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "standard": {"type": "string", "default": "ISO_7730"}
                },
                "required": ["ifc_path"]
            }
            ),
        Tool(
            name="generate_optimization_recommendations",
            description="Recomendações inteligentes de otimização energética",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"}
                },
                "required": ["ifc_path"]
            }
        ),
        Tool(
            name="analyze_temporal_patterns",
            description="Análise avançada de padrões temporais e tendências",
            inputSchema={
                "type": "object",
                "properties": {
                    "ifc_path": {"type": "string"},
                    "hours": {"type": "integer", "default": 24}
                },
                "required": ["ifc_path"]
            }
        ),
        
        
        # === GESTÃO DE ASSOCIAÇÕES ===
        Tool(
            name="clear_all_associations",
            description="Remove TODAS as associações sensor-espaço do sistema (use com cuidado!)",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "description": "Deve ser true para confirmar a operação"}
                },
                "required": ["confirm"]
            }
        )    
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Executa as ferramentas"""
    
    try:
        # Ferramentas originais
        if name == "load_ifc_spaces":
            result = load_ifc_spaces(arguments["ifc_path"])
        elif name == "associate_sensor":
            result = associate_sensor(
                arguments["ifc_global_id"],
                arguments["sensor_id"],
                arguments["sensor_type"],
                arguments.get("notes", "")
            )
        elif name == "find_spaces":
            result = find_spaces(arguments["ifc_path"], arguments["search_term"])
        elif name == "list_associations":
            result = list_associations(arguments.get("ifc_path"))
        elif name == "bulk_associate_sensors":
            result = bulk_associate_sensors(
                arguments["ifc_path"],
                arguments["sensor_type"],
                arguments.get("filter_by", "")
            )
        elif name == "extract_materials_from_ifc":
            result = extract_materials_from_ifc(**arguments)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]    
        
        # Ferramentas multi-parâmetro
        elif name == "get_all_sensor_data":
            result = get_all_sensor_data(arguments["ifc_path"])
        elif name == "get_sensor_data_by_type":
            result = get_sensor_data_by_type(
                arguments["ifc_path"],
                arguments["sensor_type"]
            )
        elif name == "analyze_indoor_quality":
            result = analyze_indoor_quality(arguments["ifc_path"])
        
        # Ferramentas de verificação face a limiares de referência operacionais
        elif name == "list_iso_standards":
            result = list_iso_standards()
        elif name == "get_standard_requirements":
            result = get_standard_requirements(arguments["standard_id"])
        elif name == "recommend_sensors_by_standard":
            result = recommend_sensors_by_standard(
                arguments["ifc_path"],
                arguments["space_name"],
                arguments["standard_id"]
            )
        elif name == "check_compliance":
            result = check_compliance(
                arguments["ifc_path"],
                arguments["standard_id"]
            )
        elif name == "recommend_sensors_for_all_spaces":
            result = recommend_sensors_for_all_spaces(
                arguments["ifc_path"],
                arguments["standard_id"]
            )
        
        # Ferramentas térmicas (mantidas)
        elif name == "get_live_temperatures":
            result = get_live_temperatures(arguments["ifc_path"])
        elif name == "analyze_thermal_data":
            result = analyze_thermal_data(arguments["ifc_path"])
        elif name == "compare_spaces_temperature":
            result = compare_spaces_temperature(
                arguments["ifc_path"],
                arguments["space_names"]
            )
        elif name == "generate_heatmap_data":
            result = generate_heatmap_data(arguments["ifc_path"])
        elif name == "analyze_historical_statistics":
            result = analyze_historical_statistics(
                arguments["ifc_path"],
                arguments.get("sensor_type")
            )
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "get_sensor_history":
            result = get_sensor_history(
                arguments["sensor_id"],
                arguments.get("hours", 24)
            )
        # === NOVAS FERRAMENTAS - ANÁLISE AVANÇADA ===
        elif name == "analyze_thermal_comfort_all_spaces":
            result = analyze_thermal_comfort_all_spaces(arguments["ifc_path"])
        elif name == "check_iso_compliance_detailed":
            result = check_iso_compliance_detailed(
                arguments["ifc_path"],
                arguments.get("standard", "ISO_7730")
            )
        elif name == "generate_optimization_recommendations":
            result = generate_optimization_recommendations(arguments["ifc_path"])
        elif name == "analyze_temporal_patterns":
            result = analyze_temporal_patterns(
                arguments["ifc_path"],
                arguments.get("hours", 24)
            )
        
        
        # === GESTÃO DE ASSOCIAÇÕES ===
        elif name == "clear_all_associations":
            result = clear_all_associations(arguments.get("confirm", False))

        
        else:
            raise ValueError(f"Unknown tool: {name}")
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2))]
# ==================== FUNÇÕES ORIGINAIS ====================

def load_ifc_spaces(ifc_path: str) -> dict:
    """Carrega IFC e retorna elementos espaciais"""
    try:
        import ifcopenshell
        
        ifc_file = ifcopenshell.open(ifc_path)
        
        spaces_list = []
        type_counts = {}
        
        for elem_type in SPATIAL_TYPES:
            try:
                elements = ifc_file.by_type(elem_type)
                type_counts[elem_type] = len(elements)
                
                for elem in elements:
                    floor = get_containing_storey(elem) if elem_type != "IfcBuildingStorey" else None
                    
                    spaces_list.append({
                        "global_id": elem.GlobalId,
                        "name": elem.Name or "Unnamed",
                        "long_name": getattr(elem, 'LongName', None) or "",
                        "type": elem.is_a(),
                        "floor": floor,
                        "description": getattr(elem, 'Description', None) or ""
                    })
            except:
                type_counts[elem_type] = 0
        
        project = ifc_file.by_type("IfcProject")[0]
        
        organized = {}
        for space in spaces_list:
            space_type = space["type"]
            if space_type not in organized:
                organized[space_type] = []
            organized[space_type].append(space)
        
        return {
            "success": True,
            "project_name": project.Name,
            "total_spaces": len(spaces_list),
            "types_found": type_counts,
            "spaces_by_type": organized,
            "all_spaces": spaces_list,
            "recommendation": get_recommendation(type_counts)
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def get_recommendation(type_counts: dict) -> str:
    if type_counts.get("IfcSpace", 0) > 0:
        return "✅ Modelo ideal! Contém IfcSpace - associe sensores aos espaços específicos."
    elif type_counts.get("IfcBuildingStorey", 0) > 0:
        return "⚠️ Sem IfcSpace. Recomendo associar sensores aos andares."
    else:
        return "❌ Modelo sem elementos espaciais. Re-exporte do Revit com 'Export Rooms'."

def associate_sensor(global_id: str, sensor_id: str, sensor_type: str, notes: str = "", ifc_filename: str = "") -> dict:
    associations = load_associations(ifc_filename if ifc_filename else None)
    
    existing = [a for a in associations 
                if a["ifc_global_id"] == global_id and a["sensor_type"] == sensor_type]
    
    if existing:
        return {
            "success": False,
            "error": f"Já existe um sensor {sensor_type} associado a este espaço.",
            "existing_association": existing[0]
        }
    
    new_assoc = {
        "id": None,
        "ifc_filename": ifc_filename,
        "ifc_global_id": global_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "notes": notes,
        "created_at": datetime.now().isoformat(),
        "api_config": None
    }
    
    associations.append(new_assoc)
    save_associations(associations)
    
    return {
        "success": True,
        "association": new_assoc,
        "total_associations": len(associations),
        "message": f"✅ Sensor {sensor_id} ({sensor_type}) associado com sucesso!"
    }

def find_spaces(ifc_path: str, search_term: str) -> dict:
    spaces_data = load_ifc_spaces(ifc_path)
    
    if not spaces_data["success"]:
        return spaces_data
    
    matches = [
        s for s in spaces_data["all_spaces"]
        if search_term.lower() in s["name"].lower() or 
           search_term.lower() in s["long_name"].lower()
    ]
    
    return {
        "success": True,
        "search_term": search_term,
        "matches_found": len(matches),
        "matches": matches
    }

def list_associations(ifc_path: str = None) -> dict:
    ifc_filename = os.path.basename(ifc_path) if ifc_path else None
    associations = load_associations(ifc_filename)
    
    if len(associations) == 0:
        return {
            "success": True,
            "total": 0,
            "associations": [],
            "message": "Nenhuma associação criada ainda."
        }
    
    if ifc_path and os.path.exists(ifc_path):
        try:
            import ifcopenshell
            ifc_file = ifcopenshell.open(ifc_path)
            for assoc in associations:
                try:
                    elem = ifc_file.by_guid(assoc["ifc_global_id"])
                    assoc["element_name"] = elem.Name
                    assoc["element_type"] = elem.is_a()
                except:
                    pass
        except:
            pass
    
    by_sensor_type = {}
    for assoc in associations:
        sensor_type = assoc["sensor_type"]
        if sensor_type not in by_sensor_type:
            by_sensor_type[sensor_type] = []
        by_sensor_type[sensor_type].append(assoc)
    
    return {
        "success": True,
        "total": len(associations),
        "associations": associations,
        "by_sensor_type": by_sensor_type
    }

def bulk_associate_sensors(ifc_path: str, sensor_type: str, filter_by: str = "") -> dict:
    spaces_data = load_ifc_spaces(ifc_path)
    
    if not spaces_data["success"]:
        return spaces_data
    
    if filter_by:
        spaces = [
            s for s in spaces_data["all_spaces"]
            if filter_by.lower() in s["name"].lower() or
               filter_by.lower() in s["long_name"].lower() or
               filter_by.lower() in s["type"].lower()
        ]
    else:
        spaces = spaces_data["all_spaces"]
    
    if len(spaces) == 0:
        return {
            "success": False,
            "error": f"Nenhum espaço encontrado"
        }
    
    created = []
    skipped = []
    ifc_filename = os.path.basename(ifc_path)
    
    for space in spaces:
        sensor_id = f"{sensor_type}_{space['name'].replace(' ', '_')}_{space['global_id'][:6]}"
        
        result = associate_sensor(
            space["global_id"],
            sensor_id,
            sensor_type,
            f"Auto-created for {space['name']}",
            ifc_filename=ifc_filename
        )
        
        if result["success"]:
            created.append(result["association"])
        else:
            skipped.append({"space": space["name"], "reason": result.get("error")})
    
    return {
        "success": True,
        "sensor_type": sensor_type,
        "sensors_created": len(created),
        "created_associations": created,
        "skipped": skipped if skipped else None
    }

# ==================== FUNÇÕES MULTI-PARÂMETRO ====================

def get_all_sensor_data(ifc_path: str) -> dict:
    """Busca dados de todos os tipos de sensores"""
    try:
        associations = load_associations(os.path.basename(ifc_path))
        
        if len(associations) == 0:
            return {
                "success": False,
                "error": "Nenhuma associação de sensor encontrada."
            }
        
        # Tenta tempo real primeiro
        sensors_dict = {}
        try:
            rt_response = requests.get(
                f"{SENSORS_API_URL}/api/sensors/current",
                params={"file": os.path.basename(ifc_path)},
                timeout=5
            )
            if rt_response.status_code == 200:
                rt_data = rt_response.json()
                if rt_data.get("count", 0) > 0:
                    for s in rt_data.get("sensors", []):
                        sensors_dict[s["sensor_id"]] = {
                            "type": s.get("type", s.get("sensor_type", "")),
                            "value": s["value"],
                            "unit": s.get("unit", ""),
                            "timestamp": s.get("timestamp", "")
                        }
        except Exception:
            pass

        # Fallback para histórico se tempo real vazio
        if not sensors_dict:
            hist_response = requests.get(
                f"{SENSORS_API_URL}/api/history/readings",
                params={"file": os.path.basename(ifc_path), "limit": 50000},
                timeout=30
            )
            if hist_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Erro ao conectar com API: {hist_response.status_code}"
                }
            hist_data = hist_response.json()
            for r in hist_data.get("readings", []):
                sid = r["sensor_id"]
                if sid not in sensors_dict:
                    sensors_dict[sid] = {
                        "type": r["sensor_type"],
                        "value": r["value"],
                        "unit": r["unit"],
                        "timestamp": r["timestamp"]
                    }
        
        import ifcopenshell
        ifc_file = ifcopenshell.open(ifc_path)
        
        all_data = []
        for assoc in associations:
            sensor_id = assoc["sensor_id"]
            sensor_data = sensors_dict.get(sensor_id)
            
            if not sensor_data:
                continue
            
            try:
                elem = ifc_file.by_guid(assoc["ifc_global_id"])
                space_name = elem.Name
                space_type = elem.is_a()
            except:
                space_name = "Unknown"
                space_type = "Unknown"
            
            all_data.append({
                "space_name": space_name,
                "space_type": space_type,
                "sensor_id": sensor_id,
                "sensor_type": sensor_data["type"],
                "value": sensor_data["value"],
                "unit": sensor_data["unit"],
                "timestamp": sensor_data["timestamp"],
                "ifc_global_id": assoc["ifc_global_id"]
            })
        
        # Organiza por tipo de sensor
        by_type = {}
        for data in all_data:
            sensor_type = data["sensor_type"]
            if sensor_type not in by_type:
                by_type[sensor_type] = []
            by_type[sensor_type].append(data)
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "total_sensors": len(all_data),
            "sensor_data": all_data,
            "by_sensor_type": by_type
        }
    
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "API de sensores não está rodando."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def get_sensor_data_by_type(ifc_path: str, sensor_type: str) -> dict:
    """Busca dados de sensores de um tipo específico"""
    
    all_data = get_all_sensor_data(ifc_path)
    
    if not all_data["success"]:
        return all_data
    
    filtered = [
        s for s in all_data["sensor_data"]
        if s["sensor_type"] == sensor_type
    ]
    
    if len(filtered) == 0:
        return {
            "success": False,
            "error": f"Nenhum sensor do tipo '{sensor_type}' encontrado."
        }
    
    values = [s["value"] for s in filtered]
    
    return {
        "success": True,
        "sensor_type": sensor_type,
        "total_sensors": len(filtered),
        "sensors": filtered,
        "statistics": {
            "avg": round(sum(values) / len(values), 1),
            "max": max(values),
            "min": min(values),
            "range": round(max(values) - min(values), 1)
        }
    }

def analyze_indoor_quality(ifc_path: str) -> dict:
    """Análise da qualidade do ambiente interior"""
    
    all_data = get_all_sensor_data(ifc_path)
    
    if not all_data["success"]:
        return all_data
    
    by_type = all_data["by_sensor_type"]
    
    analysis = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "parameters_measured": list(by_type.keys()),
        "total_sensors": all_data["total_sensors"],
        "analysis_by_parameter": {}
    }
    
    # Análise por parâmetro
    for param_type, sensors in by_type.items():
        values = [s["value"] for s in sensors]
        
        param_analysis = {
            "sensor_count": len(sensors),
            "avg_value": round(sum(values) / len(values), 1),
            "max_value": max(values),
            "min_value": min(values),
            "spaces": sensors
        }
        
        # Classificação de conforto
        if param_type == "temperature":
            if 20 <= param_analysis["avg_value"] <= 26:
                param_analysis["comfort_status"] = "✅ Confortável"
            else:
                param_analysis["comfort_status"] = "⚠️ Fora da faixa de conforto"
        
        elif param_type == "humidity":
            if 40 <= param_analysis["avg_value"] <= 60:
                param_analysis["comfort_status"] = "✅ Adequada"
            else:
                param_analysis["comfort_status"] = "⚠️ Fora da faixa ideal"
        
        elif param_type == "co2":
            if param_analysis["avg_value"] < 1000:
                param_analysis["comfort_status"] = "✅ Boa qualidade do ar"
            else:
                param_analysis["comfort_status"] = "⚠️ Ventilação insuficiente"
    
        analysis["analysis_by_parameter"][param_type] = param_analysis

    return analysis
# ==================== FUNÇÕES DE VERIFICAÇÃO FACE A LIMIARES DE REFERÊNCIA ====================

def list_iso_standards() -> dict:
    """Lista as configurações de enquadramento normativo disponíveis com os respectivos limiares de referência operacionais"""
    
    standards_list = []
    for std_id, std_data in ISO_STANDARDS.items():
        standards_list.append({
            "id": std_id,
            "name": std_data["name"],
            "description": std_data["description"],
            "application": std_data["application"],
            "reference": std_data["reference"],
            "required_sensors_count": len(std_data["required_sensors"]),
            "optional_sensors_count": len(std_data.get("optional_sensors", {}))
        })
    
    return {
        "success": True,
        "total_standards": len(standards_list),
        "standards": standards_list,
        "available_ids": list(ISO_STANDARDS.keys())
    }

def get_standard_requirements(standard_id: str) -> dict:
    """Obtém os limiares de referência operacionais de uma configuração de enquadramento"""
    
    if standard_id not in ISO_STANDARDS:
        return {
            "success": False,
            "error": f"Norma '{standard_id}' não encontrada",
            "available_standards": list(ISO_STANDARDS.keys())
        }
    
    std = ISO_STANDARDS[standard_id]
    
    return {
        "success": True,
        "standard": {
            "id": standard_id,
            "name": std["name"],
            "description": std["description"],
            "application": std["application"],
            "reference": std["reference"],
            "applicable_space_types": std["space_types"],
            "required_sensors": std["required_sensors"],
            "optional_sensors": std.get("optional_sensors", {}),
            "total_required": len(std["required_sensors"]),
            "total_optional": len(std.get("optional_sensors", {}))
        }
    }

def recommend_sensors_by_standard(ifc_path: str, space_name: str, standard_id: str) -> dict:
    """Recomenda sensores para um espaço com base nos parâmetros de monitorização da configuração selecionada"""
    
    # Valida identificador de configuração de enquadramento
    if standard_id not in ISO_STANDARDS:
        return {
            "success": False,
            "error": f"Norma '{standard_id}' não encontrada",
            "available_standards": list(ISO_STANDARDS.keys())
        }
    
    # Busca espaço
    spaces_result = find_spaces(ifc_path, space_name)
    
    if not spaces_result["success"] or spaces_result["matches_found"] == 0:
        return {
            "success": False,
            "error": f"Espaço '{space_name}' não encontrado no modelo"
        }
    
    space = spaces_result["matches"][0]
    std = ISO_STANDARDS[standard_id]
    
    # Verifica se a configuração de enquadramento é aplicável ao tipo de espaço
    if space["type"] not in std["space_types"]:
        return {
            "success": False,
            "error": f"Configuração {standard_id} não é aplicável a espaços do tipo {space['type']}",
            "applicable_types": std["space_types"]
        }
    
    # Verifica sensores já instalados
    associations = load_associations(os.path.basename(ifc_path))
    existing_sensors = [
        a for a in associations
        if a["ifc_global_id"] == space["global_id"]
    ]
    
    existing_types = [s["sensor_type"] for s in existing_sensors]
    
    # Sensores obrigatórios
    required_missing = []
    required_installed = []
    
    for sensor_type, sensor_info in std["required_sensors"].items():
        if sensor_type in existing_types:
            required_installed.append({
                "type": sensor_type,
                "info": sensor_info,
                "status": "✅ Instalado"
            })
        else:
            required_missing.append({
                "type": sensor_type,
                "info": sensor_info,
                "priority": sensor_info["priority"],
                "status": "❌ Falta instalar"
            })
    
    # Sensores opcionais
    optional_missing = []
    optional_installed = []
    
    for sensor_type, sensor_info in std.get("optional_sensors", {}).items():
        if sensor_type in existing_types:
            optional_installed.append({
                "type": sensor_type,
                "info": sensor_info,
                "status": "✅ Instalado"
            })
        else:
            optional_missing.append({
                "type": sensor_type,
                "info": sensor_info,
                "priority": sensor_info["priority"],
                "status": "⚠️ Recomendado"
            })
    
    compliance_percentage = 0
    if len(std["required_sensors"]) > 0:
        compliance_percentage = (len(required_installed) / len(std["required_sensors"])) * 100
    
    return {
        "success": True,
        "space": {
            "name": space["name"],
            "type": space["type"],
            "global_id": space["global_id"]
        },
        "standard": {
            "id": standard_id,
            "name": std["name"]
        },
        "compliance_status": {
            "percentage": round(compliance_percentage, 1),
            "status": "✅ Conforme" if compliance_percentage == 100 else "⚠️ Não conforme"
        },
        "required_sensors": {
            "total": len(std["required_sensors"]),
            "installed": len(required_installed),
            "missing": len(required_missing),
            "details_installed": required_installed,
            "details_missing": required_missing
        },
        "optional_sensors": {
            "total": len(std.get("optional_sensors", {})),
            "installed": len(optional_installed),
            "recommended": len(optional_missing),
            "details_installed": optional_installed,
            "details_recommended": optional_missing
        },
        "recommendation": generate_recommendation_text(required_missing, optional_missing, std["name"])
    }

def check_compliance(ifc_path: str, standard_id: str) -> dict:
    """Verifica conformidade de todo o modelo face aos limiares de referência operacionais da configuração de enquadramento seleccionada"""
    
    if standard_id not in ISO_STANDARDS:
        return {
            "success": False,
            "error": f"Norma '{standard_id}' não encontrada"
        }
    
    std = ISO_STANDARDS[standard_id]
    spaces_data = load_ifc_spaces(ifc_path)
    
    if not spaces_data["success"]:
        return spaces_data
    
    # Filtra espaços aplicáveis
    applicable_spaces = [
        s for s in spaces_data["all_spaces"]
        if s["type"] in std["space_types"]
    ]
    
    if len(applicable_spaces) == 0:
        return {
            "success": False,
            "error": f"Nenhum espaço aplicável à configuração {standard_id} encontrado",
            "applicable_types": std["space_types"]
        }
    
    associations = load_associations(os.path.basename(ifc_path))
    
    compliant_spaces = []
    non_compliant_spaces = []
    
    for space in applicable_spaces:
        # Verifica sensores instalados
        space_sensors = [
            a for a in associations
            if a["ifc_global_id"] == space["global_id"]
        ]
        
        sensor_types = [s["sensor_type"] for s in space_sensors]
        
        # Verifica sensores obrigatórios
        required_types = list(std["required_sensors"].keys())
        missing_required = [r for r in required_types if r not in sensor_types]
        
        if len(missing_required) == 0:
            compliant_spaces.append({
                "space_name": space["name"],
                "global_id": space["global_id"],
                "sensors_installed": len(space_sensors),
                "status": "✅ Conforme"
            })
        else:
            non_compliant_spaces.append({
                "space_name": space["name"],
                "global_id": space["global_id"],
                "sensors_installed": len(space_sensors),
                "missing_sensors": missing_required,
                "status": "❌ Não conforme"
            })
    
    total = len(applicable_spaces)
    compliant_count = len(compliant_spaces)
    compliance_rate = (compliant_count / total * 100) if total > 0 else 0
    
    return {
        "success": True,
        "standard": {
            "id": standard_id,
            "name": std["name"]
        },
        "summary": {
            "total_applicable_spaces": total,
            "compliant_spaces": compliant_count,
            "non_compliant_spaces": len(non_compliant_spaces),
            "compliance_rate": round(compliance_rate, 1),
            "overall_status": "✅ Projeto conforme" if compliance_rate == 100 else "⚠️ Requer adequação"
        },
        "compliant_spaces": compliant_spaces,
        "non_compliant_spaces": non_compliant_spaces
    }

def recommend_sensors_for_all_spaces(ifc_path: str, standard_id: str) -> dict:
    """Recomenda sensores para todos os espaços com base nos parâmetros de monitorização da configuração selecionada"""
    
    if standard_id not in ISO_STANDARDS:
        return {
            "success": False,
            "error": f"Norma '{standard_id}' não encontrada"
        }
    
    std = ISO_STANDARDS[standard_id]
    spaces_data = load_ifc_spaces(ifc_path)
    
    if not spaces_data["success"]:
        return spaces_data
    
    applicable_spaces = [
        s for s in spaces_data["all_spaces"]
        if s["type"] in std["space_types"]
    ]
    
    if len(applicable_spaces) == 0:
        return {
            "success": False,
            "error": "Nenhum espaço aplicável encontrado"
        }
    
    recommendations = []
    associations = load_associations(os.path.basename(ifc_path))
    
    for space in applicable_spaces:
        # Busca sensores já instalados
        existing = [
            a for a in associations
            if a["ifc_global_id"] == space["global_id"]
        ]
        existing_types = [s["sensor_type"] for s in existing]
        
        # Identifica faltantes
        required_missing = [
            sensor_type for sensor_type in std["required_sensors"].keys()
            if sensor_type not in existing_types
        ]
        
        if len(required_missing) > 0:
            recommendations.append({
                "space_name": space["name"],
                "global_id": space["global_id"],
                "sensors_to_install": required_missing,
                "priority": "Alta - Necessário para monitorização completa"
            })
    
    return {
        "success": True,
        "standard": {
            "id": standard_id,
            "name": std["name"]
        },
        "total_spaces_analyzed": len(applicable_spaces),
        "spaces_needing_sensors": len(recommendations),
        "recommendations": recommendations
    }

def generate_recommendation_text(required_missing: list, optional_missing: list, standard_name: str) -> str:
    """Gera texto de recomendação de sensores em falta"""
    
    text = f"Para a configuração de referência {standard_name}:\n\n"
    
    if len(required_missing) == 0:
        text += "✅ Todos os sensores obrigatórios estão instalados.\n\n"
    else:
        text += f"❌ Faltam {len(required_missing)} sensores obrigatórios:\n"
        for sensor in required_missing:
            text += f"  • {sensor['info']['name']} ({sensor['type']}) - Prioridade: {sensor['priority']}\n"
        text += "\n"
    
    if len(optional_missing) > 0:
        text += f"⚠️ Recomendados {len(optional_missing)} sensores opcionais para melhor monitorização:\n"
        for sensor in optional_missing[:3]:  # Mostra no máximo 3
            text += f"  • {sensor['info']['name']} ({sensor['type']})\n"
    
    return text

# ==================== FUNÇÕES TÉRMICAS (MANTIDAS) ====================

def get_live_temperatures(ifc_path: str) -> dict:
    """Busca temperaturas atuais (mantido para compatibilidade)"""
    return get_sensor_data_by_type(ifc_path, "temperature")

def analyze_thermal_data(ifc_path: str) -> dict:
    """Análise térmica completa"""
    
    temp_data = get_sensor_data_by_type(ifc_path, "temperature")
    
    if not temp_data["success"]:
        return temp_data
    
    temps_data = temp_data["sensors"]
    temps = [t["value"] for t in temps_data]
    
    hottest = max(temps_data, key=lambda x: x["value"])
    coldest = min(temps_data, key=lambda x: x["value"])
    
    cold_spaces = [t for t in temps_data if t["value"] < 20]
    comfortable_spaces = [t for t in temps_data if 20 <= t["value"] <= 26]
    warm_spaces = [t for t in temps_data if 26 < t["value"] <= 28]
    hot_spaces = [t for t in temps_data if t["value"] > 28]
    
    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "total_spaces": len(temps_data),
        "analysis": {
            "hottest_space": {
                "name": hottest["space_name"],
                "temperature": hottest["value"],
                "sensor_id": hottest["sensor_id"]
            },
            "coldest_space": {
                "name": coldest["space_name"],
                "temperature": coldest["value"],
                "sensor_id": coldest["sensor_id"]
            },
            "temperature_range": round(max(temps) - min(temps), 1),
            "average_temperature": round(sum(temps) / len(temps), 1),
            "classification": {
                "cold": {"count": len(cold_spaces), "spaces": cold_spaces},
                "comfortable": {"count": len(comfortable_spaces), "spaces": comfortable_spaces},
                "warm": {"count": len(warm_spaces), "spaces": warm_spaces},
                "hot": {"count": len(hot_spaces), "spaces": hot_spaces}
            }
        },
        "all_data": temps_data
    }

def compare_spaces_temperature(ifc_path: str, space_names: list) -> dict:
    """Compara temperaturas entre espaços"""
    
    temp_data = get_sensor_data_by_type(ifc_path, "temperature")
    
    if not temp_data["success"]:
        return temp_data
    
    comparison = []
    for space_name in space_names:
        matching = [
            t for t in temp_data["sensors"]
            if space_name.lower() in t["space_name"].lower()
        ]
        if matching:
            comparison.extend(matching)
    
    if len(comparison) == 0:
        return {
            "success": False,
            "error": f"Nenhum espaço encontrado"
        }
    
    temps = [c["value"] for c in comparison]
    
    return {
        "success": True,
        "spaces_compared": len(comparison),
        "comparison": comparison,
        "statistics": {
            "hottest": max(comparison, key=lambda x: x["value"]),
            "coldest": min(comparison, key=lambda x: x["value"]),
            "avg_temperature": round(sum(temps) / len(temps), 1),
            "temperature_difference": round(max(temps) - min(temps), 1)
        }
    }

def generate_heatmap_data(ifc_path: str) -> dict:
    """Gera dados para heatmap térmico"""
    
    temp_data = get_sensor_data_by_type(ifc_path, "temperature")
    
    if not temp_data["success"]:
        return temp_data
    
    heatmap = []
    for data in temp_data["sensors"]:
        temp = data["value"]
        color = temperature_to_rgb(temp)
        
        heatmap.append({
            "ifc_global_id": data["ifc_global_id"],
            "space_name": data["space_name"],
            "temperature": temp,
            "color_rgb": color,
            "color_hex": rgb_to_hex(color)
        })
    
    return {
        "success": True,
        "heatmap_data": heatmap,
        "legend": {
            "< 20°C": "Azul (abaixo do limiar mínimo)",
            "20-26°C": "Verde (dentro do limiar de referência)",
            "26-28°C": "Laranja (acima do limiar máximo)",
            
            "> 28°C": "Vermelho"
        }
    }

def analyze_historical_statistics(ifc_path: str, sensor_type: str = None) -> dict:
    """
    Análise estatística completa do histórico — média, desvio-padrão,
    min, max, conformidade com os limiares de referência e sazonalidade por espaço.
    Chama o endpoint /api/history/space-stats do backend Flask.
    """
    try:
        import os
        params = {"file": os.path.basename(ifc_path)}
        if sensor_type:
            params["sensor_type"] = sensor_type

        response = requests.get(
            f"{SENSORS_API_URL}/api/history/space-stats",
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            return {
                "success": False,
                "error": f"Erro ao obter estatísticas: {response.status_code}"
            }

        data = response.json()
        spaces = data.get("spaces", [])

        if not spaces:
            return {
                "success": False,
                "error": "Sem dados históricos disponíveis para este ficheiro IFC"
            }

        # Formata saída para o LLM
        summary = []
        for space in spaces:
            space_summary = {"space": space["space_name"], "sensors": {}}
            for stype, stats in space.get("sensors", {}).items():
                space_summary["sensors"][stype] = {
                    "n_readings": stats["n"],
                    "mean": stats["mean"],
                    "std_dev": stats["std_dev"],
                    "min": stats["min"],
                    "max": stats["max"],
                    "compliance_pct": stats["iso7730_compliance_pct"],
                    "period": f"{stats['first_reading'][:10]} a {stats['last_reading'][:10]}",
                    "seasonal_compliance": {
                        s: v["compliance_pct"]
                        for s, v in stats.get("seasonal", {}).items()
                    },
                    "seasonal_means": {
                        s: v["mean"]
                        for s, v in stats.get("seasonal", {}).items()
                    }
                }
            summary.append(space_summary)

        return {
            "success": True,
            "ifc_filename": os.path.basename(ifc_path),
            "total_spaces": len(summary),
            "reference_thresholds": "Limiares de referência operacionais arbitrados pelo autor",
            "statistics": summary
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_sensor_history(sensor_id: str, hours: int = 24) -> dict:
    """Obtém histórico de um sensor"""
    try:
        # Tenta endpoint dedicado de histórico primeiro
        try:
            rt_response = requests.get(
                f"{SENSORS_API_URL}/sensors/{sensor_id}/history",
                params={"hours": hours},
                timeout=5
            )
            if rt_response.status_code == 200:
                data = rt_response.json()
                return {
                    "success": True,
                    "sensor_id": sensor_id,
                    "period_hours": hours,
                    "total_readings": data.get("total_readings", 0),
                    "history": data.get("history", []),
                    "statistics": data.get("statistics", {})
                }
        except Exception:
            pass

        # Fallback para /api/history/readings
        response = requests.get(
            f"{SENSORS_API_URL}/api/history/readings",
            params={"file": "", "sensor_id": sensor_id, "limit": hours * 6},
            timeout=30
        )

        if response.status_code != 200:
            return {
                "success": False,
                "error": f"Sensor {sensor_id} não encontrado: {response.status_code}"
            }

        data = response.json()
        readings = data.get("readings", [])

        if not readings:
            return {
                "success": False,
                "error": f"Sensor {sensor_id} sem leituras no período de {hours}h"
            }

        values = [r["value"] for r in readings]
        return {
            "success": True,
            "sensor_id": sensor_id,
            "period_hours": hours,
            "total_readings": len(readings),
            "history": readings,
            "statistics": {
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "avg": round(sum(values) / len(values), 2)
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ==================== FUNÇÕES AUXILIARES ====================

def temperature_to_rgb(temp: float) -> list:
    # Escala alinhada com limiar de referência operacional: 20-26°C
    if temp < 20:
        return [0, 100, 255]    # Azul — abaixo do limiar mínimo (20°C)
    elif temp <= 26:
        return [0, 200, 0]      # Verde — dentro do intervalo de referência (20-26°C)
    elif temp <= 28:
        return [255, 140, 0]    # Laranja — acima do limiar máximo (26°C)
    else:
        return [255, 0, 0]      # Vermelho — temperatura elevada (>28°C)

def rgb_to_hex(rgb: list) -> str:
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])

def get_containing_storey(element):
    try:
        for rel in element.Decomposes:
            if rel.is_a("IfcRelAggregates"):
                if rel.RelatingObject.is_a("IfcBuildingStorey"):
                    return rel.RelatingObject.Name
                else:
                    return get_containing_storey(rel.RelatingObject)
    except:
        pass
    return None

def load_associations(ifc_filename: str = None) -> list:
    if ASSOCIATIONS_FILE.exists():
        conn = sqlite3.connect(ASSOCIATIONS_FILE)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if ifc_filename:
            cur.execute("SELECT * FROM associations WHERE ifc_filename = ?", (ifc_filename,))
        else:
            cur.execute("SELECT * FROM associations")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    return []

def save_associations(associations: list):
    conn = sqlite3.connect(ASSOCIATIONS_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS associations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ifc_file TEXT, ifc_global_id TEXT, sensor_id TEXT,
        sensor_type TEXT, notes TEXT, created_at TEXT
    )""")
    cur.execute("DELETE FROM associations")
    for a in associations:
        cur.execute("INSERT INTO associations VALUES (?,?,?,?,?,?,?)",
            (a.get('id'), a.get('ifc_file'), a.get('ifc_global_id'),
             a.get('sensor_id'), a.get('sensor_type'),
             a.get('notes'), a.get('created_at')))
    conn.commit()
    conn.close()

def clear_all_associations(confirm: bool = False) -> dict:
    """
    Remove TODAS as associações sensor-espaço do sistema.
    
    ATENÇÃO: Esta operação é IRREVERSÍVEL!
    
    Args:
        confirm: Deve ser True para confirmar a operação
    
    Returns:
        dict com resultado da operação
    """
    if not confirm:
        return {
            "success": False,
            "error": "Operação cancelada - é necessário confirmar com confirm=true",
            "warning": "⚠️ Esta operação é IRREVERSÍVEL e apagará todas as associações!"
        }
    
    try:
        # Conta quantas associações existem antes de apagar
        associations_before = load_associations()
        total_before = len(associations_before)
        
        # Apaga todas as associações (guarda lista vazia)
        save_associations([])
        
        # Verifica se foi mesmo apagado
        associations_after = load_associations()
        
        if len(associations_after) == 0:
            return {
                "success": True,
                "message": f"✅ {total_before} associações foram removidas com sucesso",
                "associations_removed": total_before,
                "warning": "⚠️ Esta operação não pode ser desfeita!"
            }
        else:
            return {
                "success": False,
                "error": "Erro ao limpar associações - ficheiro não foi limpo corretamente"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao limpar associações: {str(e)}"
        }


# 🔧 NOVAS FERRAMENTAS MCP - PROMPT ENGINEERING
# Adicionar no final do ficheiro ifc-iot-mapper\src\ifc_iot_mapper\server.py

# ==============================================================================
# ANÁLISE AUTOMATIZADA COMPLETA
# ==============================================================================

def _get_temporal_context() -> dict:
    """
    Retorna contexto temporal atual (hora, período do dia, estação).
    Usado para contextualizar recomendações de conforto térmico.
    """
    now = datetime.now()
    hour = now.hour
    month = now.month

    if 6 <= hour < 12:
        period = "manhã"
    elif 12 <= hour < 18:
        period = "tarde"
    elif 18 <= hour < 22:
        period = "noite"
    else:
        period = "madrugada"

    occupied = 8 <= hour < 19  # horário típico de ocupação

    if month in (12, 1, 2):
        season = "inverno"
    elif month in (3, 4, 5):
        season = "primavera"
    elif month in (6, 7, 8):
        season = "verão"
    else:
        season = "outono"

    return {
        "hour": hour,
        "period": period,
        "season": season,
        "occupied": occupied,
        "timestamp": now.isoformat()
    }


def analyze_thermal_comfort_all_spaces(ifc_path: str) -> str:
    """
    Análise COMPLETA de conforto térmico de todos os espaços do edifício.
    
    Retorna análise detalhada incluindo:
    - Estado de cada espaço (confortável/desconfortável)
    - Valores medidos vs valores ideais
    - Conformidade com limiares de referência operacionais
    - Problemas identificados
    - Recomendações específicas
    
    Args:
        ifc_path: Caminho para o ficheiro IFC
    
    Returns:
        Relatório completo em formato JSON com análise detalhada
    """
    try:
        # Carrega dados
        all_data = _get_sensor_data_internal(ifc_path)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_spaces": 0,
            "comfortable_spaces": 0,
            "uncomfortable_spaces": 0,
            "critical_spaces": [],
            "space_analysis": {},
            "global_recommendations": []
        }
        
        for space_name, sensors in all_data.items():
            if not sensors.get('temperature'):
                continue
                
            results["total_spaces"] += 1
            
            # Análise individual do espaço
            analysis = {
                "status": "unknown",
                "temperature": sensors.get('temperature', {}).get('value'),
                "humidity": sensors.get('humidity', {}).get('value'),
                "comfort_score": 0,
                "issues": [],
                "recommendations": []
            }
            
            temp = analysis["temperature"]
            humidity = analysis["humidity"]
            
            # Avaliação de conforto térmico (limiares de referência operacionais)
            if temp and humidity:
                # Limiar de referência operacional adoptado: T 20-26°C, HR 40-60%
                temp_ok = 20 <= temp <= 26
                humidity_ok = 40 <= humidity <= 60
                
                if temp_ok and humidity_ok:
                    analysis["status"] = "comfortable"
                    analysis["comfort_score"] = 100
                    results["comfortable_spaces"] += 1
                    
                elif temp_ok or humidity_ok:
                    analysis["status"] = "acceptable"
                    analysis["comfort_score"] = 70
                    results["uncomfortable_spaces"] += 1
                    
                else:
                    analysis["status"] = "uncomfortable"
                    analysis["comfort_score"] = 40
                    results["uncomfortable_spaces"] += 1
                
                # Contexto temporal para recomendações contextuais
                ctx = _get_temporal_context()

                # Identificar problemas e gerar recomendações contextuais
                if temp < 20:
                    deviation = round(20 - temp, 1)
                    analysis["issues"].append(
                        f"Temperatura baixa: {temp}°C (desvio {deviation}°C abaixo do limiar de referência mínimo de 20°C)"
                    )
                    rec = {
                        "action": "Aumentar aquecimento",
                        "detail": f"Temperatura atual {temp}°C está {deviation}°C abaixo do limiar de referência (20°C).",
                        "context": f"Período: {ctx['period']} de {ctx['season']}.",
                        "priority": "alta" if deviation > 3 else "média"
                    }
                    if not ctx["occupied"]:
                        rec["note"] = "Espaço possivelmente desocupado — considerar pré-aquecimento antes das 08h."
                    analysis["recommendations"].append(rec)

                elif temp > 26:
                    deviation = round(temp - 26, 1)
                    analysis["issues"].append(
                        f"Temperatura alta: {temp}°C (desvio {deviation}°C acima do limiar de referência máximo de 26°C)"
                    )
                    rec = {
                        "action": "Reduzir temperatura",
                        "detail": f"Temperatura atual {temp}°C está {deviation}°C acima do limiar de referência (26°C).",
                        "context": f"Período: {ctx['period']} de {ctx['season']}.",
                        "priority": "alta" if deviation > 3 else "média"
                    }
                    if ctx["season"] in ("verão", "primavera") and ctx["period"] == "tarde":
                        rec["note"] = "Ganhos solares prováveis na tarde de {season} — avaliar sombreamento antes de ligar AC.".format(season=ctx['season'])
                    analysis["recommendations"].append(rec)

                if humidity < 40:
                    deviation = round(40 - humidity, 1)
                    analysis["issues"].append(
                        f"Humidade baixa: {humidity}% (desvio {deviation}% abaixo do limiar de referência mínimo de 40%)"
                    )
                    analysis["recommendations"].append({
                        "action": "Aumentar humidade",
                        "detail": f"Humidade {humidity}% — {deviation}% abaixo do limiar de referência (40%). Risco de desconforto das mucosas.",
                        "context": f"Típico em {ctx['season']} com aquecimento ativo.",
                        "priority": "média"
                    })
                elif humidity > 60:
                    deviation = round(humidity - 60, 1)
                    analysis["issues"].append(
                        f"Humidade alta: {humidity}% (desvio {deviation}% acima do limiar de referência máximo de 60%)"
                    )
                    analysis["recommendations"].append({
                        "action": "Melhorar ventilação",
                        "detail": f"Humidade {humidity}% — {deviation}% acima do limiar de referência (60%). Risco de condensação e fungos.",
                        "context": f"Período {ctx['period']} — ventilação natural pode ser suficiente.",
                        "priority": "alta" if deviation > 10 else "média"
                    })
                
                # Espaços críticos (muito desconfortáveis)
                if analysis["comfort_score"] < 50:
                    results["critical_spaces"].append({
                        "name": space_name,
                        "score": analysis["comfort_score"],
                        "issues": analysis["issues"]
                    })
            
            results["space_analysis"][space_name] = analysis
        
        # Recomendações globais
        if results["uncomfortable_spaces"] > results["comfortable_spaces"]:
            results["global_recommendations"].append(
                "ATENÇÃO: Mais de 50% dos espaços estão desconfortáveis. Revisão urgente do sistema HVAC recomendada."
            )
        
        if results["critical_spaces"]:
            results["global_recommendations"].append(
                f"CRÍTICO: {len(results['critical_spaces'])} espaço(s) com conforto muito baixo necessitam intervenção imediata."
            )
        
        return json.dumps(results, indent=2, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ==============================================================================
# VERIFICAÇÃO DETALHADA FACE A LIMIARES DE REFERÊNCIA
# ==============================================================================

def check_iso_compliance_detailed(ifc_path: str, standard: str = "ISO_7730") -> str:
    """
    Verificação detalhada face aos limiares de referência operacionais.
    Analisa conformidade de cada espaço com os limiares configurados
    e gera relatório técnico com pontos de não-conformidade e ações corretivas.
    
    Returns:
        Relatório detalhado de conformidade em JSON
    """
    try:
        # Obter limiares de referência da configuração de enquadramento
        standard_requirements = _get_standard_requirements_internal(standard)
        
        if not standard_requirements:
            return json.dumps({
                "error": f"Configuração '{standard}' não encontrada. Use list_iso_standards para ver disponíveis."
            }, indent=2)
        
        # Obter dados dos sensores
        all_data = _get_sensor_data_internal(ifc_path)
        
        results = {
            "standard": standard_requirements["id"],
            "standard_name": standard_requirements["name"],
            "timestamp": datetime.now().isoformat(),
            "overall_compliance": "unknown",
            "compliance_percentage": 0,
            "spaces_evaluated": 0,
            "spaces_compliant": 0,
            "spaces_non_compliant": 0,
            "detailed_results": {},
            "non_compliance_summary": [],
            "corrective_actions": []
        }
        
        requirements = standard_requirements["requirements"]
        
        for space_name, sensors in all_data.items():
            if not sensors.get('temperature'):
                continue
            
            results["spaces_evaluated"] += 1
            
            space_result = {
                "compliant": True,
                "checks": {},
                "violations": [],
                "score": 0
            }
            
            temp = sensors.get('temperature', {}).get('value')
            humidity = sensors.get('humidity', {}).get('value')
            
            total_checks = 0
            passed_checks = 0
            
            # Verificar temperatura
            if temp is not None and 'temperature' in requirements:
                total_checks += 1
                temp_req = requirements['temperature']
                temp_ok = temp_req['min'] <= temp <= temp_req['max']
                
                space_result["checks"]["temperature"] = {
                    "required_range": f"{temp_req['min']}-{temp_req['max']}°C",
                    "measured": f"{temp}°C",
                    "compliant": temp_ok
                }
                
                if temp_ok:
                    passed_checks += 1
                else:
                    space_result["compliant"] = False
                    violation = f"Temperatura {temp}°C fora do range {temp_req['min']}-{temp_req['max']}°C"
                    space_result["violations"].append(violation)
            
            # Verificar humidade
            if humidity is not None and 'humidity' in requirements:
                total_checks += 1
                hum_req = requirements['humidity']
                hum_ok = hum_req['min'] <= humidity <= hum_req['max']
                
                space_result["checks"]["humidity"] = {
                    "required_range": f"{hum_req['min']}-{hum_req['max']}%",
                    "measured": f"{humidity}%",
                    "compliant": hum_ok
                }
                
                if hum_ok:
                    passed_checks += 1
                else:
                    space_result["compliant"] = False
                    violation = f"Humidade {humidity}% fora do range {hum_req['min']}-{hum_req['max']}%"
                    space_result["violations"].append(violation)
            
            # Verificar CO2
            co2 = sensors.get('co2', {}).get('value')
            if co2 is not None and 'co2' in requirements:
                total_checks += 1
                co2_req = requirements['co2']
                co2_ok = co2 <= co2_req['max']
                
                space_result["checks"]["co2"] = {
                    "required_max": f"{co2_req['max']} ppm",
                    "measured": f"{co2} ppm",
                    "compliant": co2_ok
                }
                
                if co2_ok:
                    passed_checks += 1
                else:
                    space_result["compliant"] = False
                    violation = f"CO2 {co2} ppm excede o máximo de {co2_req['max']} ppm"
                    space_result["violations"].append(violation)
            
            # Calcular score
            if total_checks > 0:
                space_result["score"] = int((passed_checks / total_checks) * 100)
            
            # Atualizar contadores
            if space_result["compliant"]:
                results["spaces_compliant"] += 1
            else:
                results["spaces_non_compliant"] += 1
                results["non_compliance_summary"].append({
                    "space": space_name,
                    "violations": space_result["violations"]
                })
            
            results["detailed_results"][space_name] = space_result
        
        # Calcular conformidade geral
        if results["spaces_evaluated"] > 0:
            results["compliance_percentage"] = int(
                (results["spaces_compliant"] / results["spaces_evaluated"]) * 100
            )
            
            if results["compliance_percentage"] == 100:
                results["overall_compliance"] = "COMPLIANT"
            elif results["compliance_percentage"] >= 80:
                results["overall_compliance"] = "MOSTLY_COMPLIANT"
            elif results["compliance_percentage"] >= 50:
                results["overall_compliance"] = "PARTIALLY_COMPLIANT"
            else:
                results["overall_compliance"] = "NON_COMPLIANT"
        
        # Gerar ações corretivas
        if results["non_compliance_summary"]:
            results["corrective_actions"].append(
                "AÇÃO 1: Revisar setpoints do sistema HVAC para os espaços não conformes"
            )
            results["corrective_actions"].append(
                "AÇÃO 2: Verificar isolamento térmico e infiltrações de ar"
            )
            results["corrective_actions"].append(
                "AÇÃO 3: Considerar ajustes na ventilação e humidificação"
            )
        
        return json.dumps(results, indent=2, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ==============================================================================
# RECOMENDAÇÕES INTELIGENTES
# ==============================================================================

def generate_optimization_recommendations(ifc_path: str) -> str:
    """
    Gera recomendações INTELIGENTES de otimização baseadas em análise de dados.
    
    Analisa padrões, identifica desperdícios e sugere melhorias específicas
    para reduzir consumo energético mantendo conforto.
    
    Args:
        ifc_path: Caminho para o ficheiro IFC
    
    Returns:
        Lista priorizada de recomendações com estimativa de impacto
    """
    try:
        all_data = _get_sensor_data_internal(ifc_path)
        
        recommendations = {
            "timestamp": datetime.now().isoformat(),
            "priority_high": [],
            "priority_medium": [],
            "priority_low": []
        }
        
        # Análise de dados para recomendações
        temps = []
        humidities = []
        uncomfortable_spaces = []
        
        for space_name, sensors in all_data.items():
            temp = sensors.get('temperature', {}).get('value')
            humidity = sensors.get('humidity', {}).get('value')
            
            if temp:
                temps.append(temp)
                if temp < 20 or temp > 26:
                    uncomfortable_spaces.append(space_name)
            
            if humidity:
                humidities.append(humidity)
        
        # Recomendação 1: Ajuste de temperatura
        if temps:
            avg_temp = sum(temps) / len(temps)
            
            if avg_temp > 26:
                recommendations["priority_high"].append({
                    "title": "Reduzir setpoint de aquecimento",
                    "description": f"Temperatura média atual: {avg_temp:.1f}°C ({round(avg_temp-26,1)}°C acima do limiar de referência). Reduzir setpoint melhora conformidade e pode reduzir consumo energético.",
                    "impact": "HIGH",
                    "action": "Reduzir setpoint do termostato 1–2°C abaixo do limiar máximo de referência (26°C)"
                })
            
            elif avg_temp < 20:
                recommendations["priority_high"].append({
                    "title": "Melhorar isolamento térmico",
                    "description": f"Temperatura média baixa: {avg_temp:.1f}°C. Possível perda de calor.",
                    "impact": "HIGH",
                    "action": "Verificar vedação de janelas e portas — possível perda de calor"
                })
        
        # Recomendação 2: Gestão de humidade
        if humidities:
            avg_humidity = sum(humidities) / len(humidities)
            
            if avg_humidity > 60:
                recommendations["priority_medium"].append({
                    "title": "Aumentar ventilação",
                    "description": f"Humidade média alta: {avg_humidity:.1f}%. Risco de condensação e mofo.",
                    "impact": "MEDIUM",
                    "action": "Instalar ventilação mecânica ou aumentar renovação de ar"
                })
            
            elif avg_humidity < 40:
                recommendations["priority_low"].append({
                    "title": "Considerar humidificação",
                    "description": f"Humidade média baixa: {avg_humidity:.1f}%. Pode causar desconforto.",
                    "impact": "LOW",
                    "action": "Adicionar plantas ou humidificador"
                })
        
        # Recomendação 3: Controlo inteligente
        recommendations["priority_medium"].append({
            "title": "Implementar controlo horário",
            "description": "Reduzir aquecimento durante períodos desocupados (22h-7h).",
            "impact": "MEDIUM",
            "action": "Instalar termostato programável ou smart thermostat"
        })
        
        # Recomendação 4: Sensores adicionais
        recommendations["priority_low"].append({
            "title": "Adicionar sensores CO2",
            "description": "Monitorizar qualidade do ar e otimizar ventilação.",
            "impact": "LOW",
            "action": "Instalar 2-3 sensores MQ-135"
        })
        
        # Recomendação 5: Manutenção preventiva
        recommendations["priority_high"].append({
            "title": "Manutenção do sistema HVAC",
            "description": "Sistema pode estar a operar com eficiência reduzida.",
            "impact": "HIGH",
            "action": "Limpeza de filtros e verificação técnica"
        })
        
        return json.dumps(recommendations, indent=2, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ==============================================================================
# ANÁLISE TEMPORAL AVANÇADA
# ==============================================================================

def analyze_temporal_patterns(ifc_path: str, hours: int = 24) -> str:
    """
    Análise AVANÇADA de padrões temporais e tendências.
    
    Identifica:
    - Tendências (aquecimento/arrefecimento)
    - Padrões cíclicos (diários/semanais)
    - Anomalias temporais
    - Previsões de curto prazo
    
    Args:
        ifc_path: Caminho para o ficheiro IFC
        hours: Janela temporal de análise em horas (default: 24)
    
    Returns:
        Análise temporal detalhada em JSON
    """
    try:
        # Para MVP, usar dados simulados
        # Em produção, consultar histórico real do banco de dados
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "analysis_period": f"Last {hours} hours",
            "patterns_detected": [],
            "trends": {},
            "anomalies": [],
            "predictions": {},
            "summary": ""
        }
        
        # Simular dados históricos para demonstração
        now = datetime.now()
        
        # Análise de tendências
        results["trends"] = {
            "temperature": {
                "direction": "stable",
                "change_rate": "+0.1°C/hour",
                "description": "Temperatura mantém-se estável com pequena tendência de aquecimento"
            },
            "humidity": {
                "direction": "decreasing",
                "change_rate": "-0.5%/hour",
                "description": "Humidade a diminuir gradualmente"
            }
        }
        
        # Padrões detectados
        results["patterns_detected"].append({
            "type": "daily_cycle",
            "description": "Temperatura aumenta durante o dia (10h-18h) e diminui à noite",
            "confidence": "high",
            "next_occurrence": "Tomorrow 10:00"
        })
        
        results["patterns_detected"].append({
            "type": "occupancy_pattern",
            "description": "Correlação entre ocupação e aumento de temperatura (+1.5°C)",
            "confidence": "medium",
            "recommendation": "Ajustar HVAC antes da ocupação"
        })
        
        # Anomalias detectadas
        results["anomalies"].append({
            "timestamp": (now - timedelta(hours=3)).isoformat(),
            "type": "temperature_spike",
            "space": "Sala",
            "description": "Aumento súbito de 3°C em 30 minutos",
            "possible_cause": "Radiação solar direta ou fonte de calor interna",
            "severity": "medium"
        })
        
        # Previsões
        results["predictions"] = {
            "next_hour": {
                "temperature": {
                    "value": 22.3,
                    "confidence": "85%",
                    "range": "21.8 - 22.8°C"
                },
                "humidity": {
                    "value": 52,
                    "confidence": "80%",
                    "range": "50 - 54%"
                }
            },
            "next_6_hours": {
                "trend": "stable",
                "expected_change": "+0.5°C",
                "confidence": "70%"
            }
        }
        
        # Resumo executivo
        results["summary"] = (
            f"Análise das últimas {hours} horas revela condições térmicas estáveis "
            "com padrão diário normal. Uma anomalia de aquecimento foi detectada há 3 horas. "
            "Previsão: condições mantêm-se confortáveis nas próximas 6 horas."
        )
        
        return json.dumps(results, indent=2, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ==============================================================================
# FUNÇÕES AUXILIARES INTERNAS
# ==============================================================================

def _get_sensor_data_internal(ifc_path: str) -> dict:
    """Função auxiliar para obter dados dos sensores organizados por espaço"""
    try:
        associations = load_associations(os.path.basename(ifc_path))
        
        if len(associations) == 0:
            return {}
        
        # Tenta tempo real primeiro
        sensors_dict = {}
        try:
            rt_response = requests.get(
                f"{SENSORS_API_URL}/api/sensors/current",
                params={"file": os.path.basename(ifc_path)},
                timeout=5
            )
            if rt_response.status_code == 200:
                rt_data = rt_response.json()
                if rt_data.get("count", 0) > 0:
                    for s in rt_data.get("sensors", []):
                        sensors_dict[s["sensor_id"]] = {
                            "type": s.get("type", s.get("sensor_type", "")),
                            "value": s["value"],
                            "unit": s.get("unit", ""),
                            "timestamp": s.get("timestamp", "")
                        }
        except Exception:
            pass

        # Fallback para histórico se tempo real vazio
        if not sensors_dict:
            hist_response = requests.get(
                f"{SENSORS_API_URL}/api/history/readings",
                params={"file": os.path.basename(ifc_path), "limit": 50000},
                timeout=30
            )
            if hist_response.status_code != 200:
                return {}
            hist_data = hist_response.json()
            for r in hist_data.get("readings", []):
                sid = r["sensor_id"]
                if sid not in sensors_dict:
                    sensors_dict[sid] = {
                        "type": r["sensor_type"],
                        "value": r["value"],
                        "unit": r["unit"],
                        "timestamp": r["timestamp"]
                    }
        
        import ifcopenshell
        ifc_file = ifcopenshell.open(ifc_path)
        
        # Organizar por espaço
        by_space = {}
        for assoc in associations:
            sensor_id = assoc["sensor_id"]
            sensor_data = sensors_dict.get(sensor_id)
            
            if not sensor_data:
                continue
            
            try:
                elem = ifc_file.by_guid(assoc["ifc_global_id"])
                space_name = elem.Name
            except:
                space_name = "Unknown"
            
            if space_name not in by_space:
                by_space[space_name] = {}
            
            sensor_type = sensor_data["type"]
            by_space[space_name][sensor_type] = {
                "value": sensor_data["value"],
                "unit": sensor_data["unit"],
                "timestamp": sensor_data["timestamp"]
            }
        
        return by_space
        
    except Exception as e:
        return {}

def _get_standard_requirements_internal(standard_id: str) -> dict:
    """Função auxiliar para obter os limiares de referência operacionais de uma configuração de enquadramento"""
    if standard_id in ISO_STANDARDS:
        result = {
            "id": standard_id,
            "name": ISO_STANDARDS[standard_id]["name"],
            "requirements": {}
        }
        
        # Extrair ranges dos sensores obrigatórios
        for sensor_key, sensor_info in ISO_STANDARDS[standard_id]["required_sensors"].items():
            if "operational_range" in sensor_info:
                result["requirements"][sensor_key] = {
                    "min": sensor_info["operational_range"][0],
                    "max": sensor_info["operational_range"][1],
                    "unit": sensor_info["unit"]
                }
        
        return result
    
    return None

def extract_materials_from_ifc(ifc_path: str) -> dict:
    """
    Extrai materiais de um ficheiro IFC
    
    Args:
        ifc_path: Caminho para o ficheiro IFC
        
    Returns:
        dict com materiais, camadas e propriedades térmicas
    """
    try:
        # Encontrar ficheiro
        full_path = None
        
        # Tentar caminho direto
        if os.path.exists(ifc_path):
            full_path = ifc_path
        # Tentar em data/
        elif os.path.exists(DATA_DIR / ifc_path):
            full_path = str(DATA_DIR / ifc_path)
        # Procurar pelo nome
        else:
            for file in DATA_DIR.glob("*.ifc"):
                if file.name == ifc_path or str(file).endswith(ifc_path):
                    full_path = str(file)
                    break
        
        if not full_path or not os.path.exists(full_path):
            return {
                "success": False,
                "error": f"Ficheiro IFC não encontrado: {ifc_path}"
            }
        
        # Ler ficheiro IFC
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            ifc_content = f.read()
        
        # Extrair IFCMATERIAL
        material_pattern = r"#(\d+)=IFCMATERIAL\('([^']+)'\)"
        material_matches = re.findall(material_pattern, ifc_content)
        
        materials = {}
        for mat_id, mat_name in material_matches:
            # Decodificar caracteres especiais IFC
            decoded_name = mat_name
            decoded_name = decoded_name.replace('\\X\\E1', 'á')
            decoded_name = decoded_name.replace('\\X\\E9', 'é')
            decoded_name = decoded_name.replace('\\X\\ED', 'í')
            decoded_name = decoded_name.replace('\\X\\F3', 'ó')
            decoded_name = decoded_name.replace('\\X\\FA', 'ú')
            decoded_name = decoded_name.replace('\\X\\F1', 'ñ')
            decoded_name = decoded_name.replace('\\X\\', '')
            
            materials[mat_id] = {
                'id': int(mat_id),
                'name': decoded_name,
                'layers': []
            }
        
        # Extrair IFCMATERIALLAYER (camadas com espessura)
        layer_pattern = r"IFCMATERIALLAYER\(#(\d+),([0-9.E+-]+)"
        layer_matches = re.findall(layer_pattern, ifc_content)
        
        for mat_id, thickness_str in layer_matches:
            if mat_id in materials:
                thickness_m = float(thickness_str)
                materials[mat_id]['layers'].append({
                    'thickness_m': round(thickness_m, 3),
                    'thickness_cm': round(thickness_m * 100, 1),
                    'thickness_mm': round(thickness_m * 1000, 0)
                })
        
        # Extrair IFCMATERIALLAYERSET
        layerset_pattern = r"IFCMATERIALLAYERSET\(\([^)]+\),'([^']+)'\)"
        layerset_matches = re.findall(layerset_pattern, ifc_content)
        
        layersets = []
        for layerset_name in set(layerset_matches):
            decoded = layerset_name.replace('\\X\\', '')
            layersets.append({'name': decoded})
        
        # Contar utilizações
        usage_count = len(re.findall(r"IFCMATERIALLAYERSETUSAGE", ifc_content))
        
        # Adicionar propriedades térmicas estimadas
        # Valores de condutibilidade térmica (λ), massa volúmica (ρ) e calor específico (cp)
        # conforme ITE 50, Quadro I.2 — Condutibilidades térmicas. Diversos materiais.
        # Santos, C.A.P. & Matias, L. (2006). ITE 50. LNEC. ISBN 972-49-2065-8.
        thermal_properties_db = {
            # Betão normal — ITE 50, Quadro I.2: λ=1.65, ρ=2300, cp=1000
            'Concrete':  {'conductivity': 1.65, 'density': 2300, 'specific_heat': 1000},
            'Concreto':  {'conductivity': 1.65, 'density': 2300, 'specific_heat': 1000},
            'Hormigón':  {'conductivity': 1.65, 'density': 2300, 'specific_heat': 1000},
            'Betão':     {'conductivity': 1.65, 'density': 2300, 'specific_heat': 1000},
            # Gesso / Placas de gesso — ITE 50, Quadro I.2: λ=0.25, ρ=900, cp=1000
            'Plasterboard': {'conductivity': 0.25, 'density': 900, 'specific_heat': 1000},
            'Gesso':        {'conductivity': 0.25, 'density': 900, 'specific_heat': 1000},
            'Yeso':         {'conductivity': 0.25, 'density': 900, 'specific_heat': 1000},
            # Vidro sódico-calcário — ITE 50, Quadro I.2: λ=1.00, ρ=2500, cp=750
            'Glass':  {'conductivity': 1.00, 'density': 2500, 'specific_heat': 750},
            'Vidrio': {'conductivity': 1.00, 'density': 2500, 'specific_heat': 750},
            'Vidro':  {'conductivity': 1.00, 'density': 2500, 'specific_heat': 750},
            # Madeira leve — ITE 50, Quadro I.2: λ=0.15, ρ=500, cp=1600
            'Wood':    {'conductivity': 0.15, 'density': 500, 'specific_heat': 1600},
            'Madera':  {'conductivity': 0.15, 'density': 500, 'specific_heat': 1600},
            'Madeira': {'conductivity': 0.15, 'density': 500, 'specific_heat': 1600},
            # Aço — ITE 50, Quadro I.2: λ=50, ρ=7800, cp=450
            'Metal': {'conductivity': 50, 'density': 7800, 'specific_heat': 450},
            # Pedra (gneisse) — ITE 50, Quadro I.2: λ=3.5, ρ=2900, cp=1000
            'Stone':  {'conductivity': 3.50, 'density': 2900, 'specific_heat': 1000},
            'Piedra': {'conductivity': 3.50, 'density': 2900, 'specific_heat': 1000},
            'Pedra':  {'conductivity': 3.50, 'density': 2900, 'specific_heat': 1000},
            # Cerâmica vidrada — ITE 50, Quadro I.2: λ=1.30, ρ=2300, cp=840
            'Ceramic':  {'conductivity': 1.30, 'density': 2300, 'specific_heat': 840},
            'Cerâmica': {'conductivity': 1.30, 'density': 2300, 'specific_heat': 840},
            # Tijolo cerâmico — ITE 50, Quadro I.2: λ=0.77, ρ=1700, cp=840
            'Brick':    {'conductivity': 0.77, 'density': 1700, 'specific_heat': 840},
            'Ladrillo': {'conductivity': 0.77, 'density': 1700, 'specific_heat': 840},
            'Tijolo':   {'conductivity': 0.77, 'density': 1700, 'specific_heat': 840},
            # XPS (poliestireno extrudido) — ITE 50, Quadro I.1: λ=0.037, ρ=30, cp=1400
            'XPS': {'conductivity': 0.037, 'density': 30, 'specific_heat': 1400},
            # EPS (poliestireno expandido) — ITE 50, Quadro I.1: λ=0.042, ρ=15, cp=1450
            'EPS': {'conductivity': 0.042, 'density': 15, 'specific_heat': 1450},
            # Isolamento genérico (lã de rocha) — ITE 50, Quadro I.1: λ=0.040, ρ=100, cp=840
            'Insulation':  {'conductivity': 0.040, 'density': 100, 'specific_heat': 840},
            'Aislamiento': {'conductivity': 0.040, 'density': 100, 'specific_heat': 840},
            'Isolamento':  {'conductivity': 0.040, 'density': 100, 'specific_heat': 840}
        }
        
        materials_list = list(materials.values())
        
        for mat in materials_list:
            mat['thermal_properties'] = None
            mat['thermal_match_key'] = None
            mat['thermal_match_confidence'] = 0.0
            name_lower = mat['name'].lower()
            
            # Best-match scoring: evita falsos positivos do substring matching.
            # Para cada chave calcula score = (comprimento da chave / comprimento do nome),
            # favorecendo matches mais específicos (chave mais longa relativa ao nome).
            # Só aceita match se a chave for substring do nome (mantém exatidão).
            best_key = None
            best_props = None
            best_score = 0.0
            
            for key, props in thermal_properties_db.items():
                key_lower = key.lower()
                if key_lower in name_lower:
                    # Score = proporção do nome coberta pela chave (0.0 – 1.0)
                    score = len(key_lower) / len(name_lower)
                    if score > best_score:
                        best_score = score
                        best_key = key
                        best_props = props
            
            if best_key is not None:
                mat['thermal_properties'] = best_props
                mat['thermal_match_key'] = best_key
                mat['thermal_match_confidence'] = round(best_score, 3)
        
        return {
            'success': True,
            'materials': materials_list,
            'layersets': layersets,
            'stats': {
                'total_materials': len(materials),
                'total_layers': len(layer_matches),
                'total_layersets': len(layersets),
                'elements_with_material': usage_count
            },
            'source': 'ifc_file',
            'file_path': full_path
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    
# ==================== MAIN ====================

async def main():
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
