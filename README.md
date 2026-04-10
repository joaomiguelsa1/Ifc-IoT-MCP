# 🏗️ VIVIENDA

**Framework de Digital Twin integrando BIM (IFC), sensores IoT e LLMs via Model Context Protocol para análise automatizada de conforto térmico em habitação social.**

> FEUP — Mestrado em Engenharia Civil 2025/2026 · João Sá · v2.3

![Python](https://img.shields.io/badge/Python-3.9--3.13-blue)
![Flask](https://img.shields.io/badge/Flask-3.0+-green)
![MCP](https://img.shields.io/badge/MCP-1.0+-purple)
![IFC](https://img.shields.io/badge/IFC-ifcopenshell%200.8+-orange)

---

## Sobre o sistema

O VIVIENDA é um framework de Digital Twin classificado como **ADTwI** (Asset Digital Twin with Intelligence) segundo a prEN 18162:2025. Integra modelos BIM em formato IFC com leituras de sensores IoT em tempo real e um LLM (Claude) via Model Context Protocol (MCP), permitindo análise automatizada de conforto térmico através de linguagem natural.

O sistema foi validado com **387.346 leituras reais** de sensores SHT85 (temperatura e humidade) provenientes de habitação social na cidade do Porto, distribuídas por 4 espaços de apartamentos renovados e não-renovados ao longo de ~13 meses.

---

## Métricas

| Métrica | Valor |
|---|---|
| Prompts na taxonomia | 95 |
| Categorias de prompts | 6 |
| Técnicas de prompt engineering | 10 |
| Leituras de validação | 387.346 |
| Ferramentas MCP disponíveis | 25+ |

---

## Arquitetura

```
Interface Web (Three.js)
        │
        ▼
Flask Backend (REST API)
        │  associations.db (SQLite)
        ▼
Servidor MCP (ifc_iot_server.py)
        │  IFC + IoT + Normas
        ▼
Claude (LLM) — linguagem natural
```

**Fluxo de dados:**
1. A interface web 3D carrega modelos IFC e visualiza os espaços e sensores associados.
2. O backend Flask gere as associações sensor-espaço e o histórico temporal em SQLite.
3. O servidor MCP expõe 25+ ferramentas especializadas ao Claude (análise IFC, dados IoT, conforto térmico, padrões temporais).
4. O Claude acede às ferramentas MCP para responder a prompts em linguagem natural com dados reais.

---

## Taxonomia de 95 Prompts

| Categoria | Nº Prompts | Descrição |
|---|---|---|
| Temporal | 38 | Análise histórica, tendências, padrões temporais |
| Diagnóstico | 14 | Identificação de problemas e anomalias |
| Operacional | 12 | Gestão de sensores e associações |
| Comparativo | 11 | Comparação entre espaços e períodos |
| Prescritivo | 11 | Recomendações e ações corretivas |
| Informativo | 9 | Consulta de dados e estado atual |

### Técnicas de prompt engineering utilizadas

- Chain-of-Thought (CoT)
- Few-Shot Prompting
- RAG Estruturado (MCP)
- Instruction Prompting
- Self-Consistency
- Self-Refine
- Chain-of-Verification (CoVe)
- Prompt Chaining
- Structured Prompts
- Meta-prompting

---

## Estrutura de ficheiros

```
vivienda/
├── ifc_iot_server.py              # Servidor MCP — 25+ ferramentas IFC/IoT
├── backend_v2_2_historico.py      # Flask REST API — SQLite, histórico temporal
├── sensor_config.py               # Configuração de sensores HTTP/MQTT/Mock
├── index_v2_1_multiprojeto.html   # Interface web 3D — Three.js, multi-projeto
├── excel_config_sens.xlsx         # Mapeamento sensor_id → IFC GlobalId
├── TAXONOMIA_95_PROMPTS.json      # Taxonomia completa dos 95 prompts
├── Configurar_claude_mcp.bat      # Setup automático Windows
├── requirements.txt               # Dependências Python
└── data/
    └── associations.db            # Base de dados SQLite
```

---

## Base de dados SQLite

O sistema utiliza uma única base de dados (`associations.db`) com três tabelas:

### `associations`
Mapeamento sensor ↔ espaço IFC.

| Campo | Tipo | Descrição |
|---|---|---|
| `ifc_filename` | TEXT | Nome do ficheiro IFC |
| `ifc_global_id` | TEXT | GlobalId do espaço IFC |
| `sensor_id` | TEXT | Identificador do sensor |
| `sensor_type` | TEXT | Tipo: temperature, humidity, co2… |
| `api_config` | TEXT | Protocolo de recolha (ncd_api, mock…) |

### `sensor_readings`
Histórico temporal de todas as leituras. Alimentado via `POST /api/sensors/ingest`.

### `association_history`
Registo de auditoria de alterações às associações sensor-espaço.

---

## Limiares de referência operacionais

> **Nota:** Os limiares abaixo são valores operacionais definidos empiricamente para validação do framework VIVIENDA. Não constituem reprodução das tabelas normativas oficiais das normas referenciadas (ISO 7730:2005, EN 16798-1:2019, ASHRAE 55:2020).
>
> Suportados empiricamente por:
> - Alegría-Sala et al. (2022) — limiares mínimos de T (20 °C) e HR (50 %) em espaços universitários
> - Arsad et al. (2023) — intervalos de conforto 22,0–28,4 °C em edifícios com climatização

| Parâmetro | Intervalo operacional |
|---|---|
| Temperatura | 20 – 26 °C |
| Humidade relativa | 40 – 60 % |

---

## Instalação

### Pré-requisitos

- Python 3.9 – 3.13
- Claude Desktop (para correr o servidor MCP)

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

Ou instalação mínima:

```bash
pip install flask flask-cors ifcopenshell mcp
```

### 2. Configurar o Claude Desktop (Windows)

Executar o script como Administrador:

```
Configurar_claude_mcp.bat
```

O script localiza automaticamente o Python e o `ifc_iot_server.py`, instala as dependências e cria o ficheiro de configuração em:

```
%APPDATA%\Claude\claude_desktop_config.json
```

Ou configurar manualmente:

```json
{
  "mcpServers": {
    "ifc-iot-mapper": {
      "command": "C:\\Path\\To\\python.exe",
      "args": ["C:\\Path\\To\\ifc_iot_server.py"]
    }
  }
}
```

### 3. Iniciar o backend Flask

```bash
python backend_v2_2_historico.py
```

API disponível em `http://localhost:5000`.

### 4. Abrir a interface web

```
http://localhost:5000/static/index_v2_1_multiprojeto.html
```

### 5. Reiniciar o Claude Desktop

Fechar completamente (incluindo o system tray) e reabrir. O ícone de martelo indica que o servidor MCP está ligado.

---

## Configuração de sensores

Cada sensor é definido no `excel_config_sens.xlsx`. A coluna `api_config` determina o protocolo de recolha:

| `api_config` | Protocolo | Descrição |
|---|---|---|
| `ncd_api` | HTTP/REST | API NCD Industrial IoT |
| `adeunis_api` | HTTP/REST | API Adeunis IoT |
| `local_gateway` | HTTP/REST | Gateway local (ex: Pressac) |
| `mock` | Simulação | Dados gerados localmente (desenvolvimento) |
| `mosquitto_local` | MQTT* | Broker Mosquitto local |
| `hivemq_cloud` | MQTT* | Broker HiveMQ Cloud |

> *MQTT está preparado arquiteturalmente em `sensor_config.py` mas não implementado funcionalmente. HTTP polling é suficiente para a escala de teste (~20 sensores).

### Exemplo de configuração no Excel

| sensor_id | ifc_global_id | sensor_type | api_config |
|---|---|---|---|
| TEMP_Q1_001 | 2X8uhRbQLEbg... | temperature | ncd_api |
| HUM_Q1_001 | 2X8uhRbQLEbg... | humidity | ncd_api |
| TEMP_Q2_002 | 1W7tgQaPKDbf... | temperature | local_gateway |
| CO2_SALA_001 | 3Y9viScRMFch... | co2 | mock |

---

## Principais endpoints REST

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/ifc/spaces` | Lista espaços do modelo IFC |
| GET | `/api/sensors/current` | Leituras atuais de todos os sensores |
| GET | `/api/sensors/list` | Lista associações sensor-espaço |
| GET | `/api/sensors/comparison` | Comparação entre espaços |
| GET | `/api/sensors/quality` | Qualidade do ar interior |
| POST | `/api/sensors/ingest` | Ingestão de leituras reais |

---

## Ferramentas MCP disponíveis (seleção)

| Ferramenta | Descrição |
|---|---|
| `load_ifc_spaces()` | Carrega e lista espaços do IFC |
| `find_spaces()` | Pesquisa espaços por nome |
| `get_all_sensor_data()` | Dados atuais de todos os sensores |
| `analyze_thermal_data()` | Análise térmica completa |
| `analyze_indoor_quality()` | Qualidade do ambiente interior |
| `analyze_thermal_comfort_all_spaces()` | Conforto térmico de todos os espaços |
| `get_sensor_history()` | Histórico de um sensor |
| `analyze_temporal_patterns()` | Padrões temporais e tendências |
| `analyze_historical_statistics()` | Estatísticas do histórico completo |
| `generate_optimization_recommendations()` | Recomendações de otimização energética |
| `associate_sensor()` | Associa sensor a espaço IFC |
| `list_associations()` | Lista todas as associações |
| `check_iso_compliance_detailed()` | Verificação face a limiares de referência |

---

## Dependências principais

```
flask>=3.0.0
flask-cors>=4.0.0
ifcopenshell>=0.8.0
mcp>=1.0.0
pandas>=2.0.0
openpyxl>=3.1.0
numpy>=1.24.0
scipy>=1.10.0
requests>=2.31.0
```

---

## Autor

**João Sá**  
Mestrado em Engenharia Civil — FEUP (Faculdade de Engenharia da Universidade do Porto)  
Dissertação: *"Engineering Prompting Para Gestão de Informação IoT em Modelos BIM"*  
2025/2026

---

*VIVIENDA v2.3 — Digital Twin BIM + IoT + LLM*
