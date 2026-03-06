"""
replace_globalids.py
====================
Script de pós-exportação IFC — substituição de GlobalIds gerados automaticamente
pelo Autodesk Revit por identificadores semanticamente legíveis.

Contexto:
    Quando um modelo BIM é exportado do Revit para formato IFC, os GlobalIds dos
    espaços (IfcSpace) são gerados automaticamente no formato UUID comprimido
    (22 caracteres base64), por exemplo: "2qYKvFEvH4cPghyPNWjr4A".
    Este script substitui esses identificadores por strings semanticamente legíveis,
    facilitando a rastreabilidade em sistemas de integração IoT–BIM como o VIVIENDA.

Requisitos:
    pip install ifcopenshell

Utilização:
    python replace_globalids.py

Autor: João Rodrigues
Dissertação: Framework de Prompt Engineering para Automatização da Análise
             de Conforto Térmico em Digital Twins BIM — FEUP, 2025/2026
"""

import ifcopenshell
import os
import shutil
from datetime import datetime

# ─── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

# Caminho para o ficheiro IFC exportado pelo Revit
INPUT_IFC = "Apartamentos_NR_Revit_Export.ifc"

# Caminho para o ficheiro IFC de saída (com GlobalIds substituídos)
OUTPUT_IFC = "Apartamentos_Validacao_VIVIENDA.ifc"

# Mapeamento: Nome do espaço (conforme definido no Revit) → GlobalId legível
# Os nomes devem corresponder exactamente ao campo Name dos IfcSpace no ficheiro IFC
GLOBALID_MAP = {
    "Quarto Renovado":     "BEDROOM-R-001",
    "Quarto Não Renovado": "BEDROOM-NR-002",
    "Sala Renovada":       "LIVINGROOM-R-003",
    "Sala Não Renovada":   "LIVINGROOM-NR-004",
}

# ─── FUNÇÕES AUXILIARES ────────────────────────────────────────────────────────

def criar_backup(caminho: str) -> str:
    """Cria uma cópia de segurança do ficheiro original antes de modificar."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{caminho}.backup_{timestamp}"
    shutil.copy2(caminho, backup)
    return backup


def listar_espacos(modelo: ifcopenshell.file) -> None:
    """Lista todos os IfcSpace encontrados no modelo com os seus GlobalIds actuais."""
    espacos = modelo.by_type("IfcSpace")
    if not espacos:
        print("  [AVISO] Nenhum IfcSpace encontrado no modelo.")
        return
    print(f"  {'GlobalId actual':<30} {'Nome':<30} {'LongName'}")
    print(f"  {'-'*30} {'-'*30} {'-'*20}")
    for e in espacos:
        long_name = e.LongName or ""
        print(f"  {e.GlobalId:<30} {e.Name or '(sem nome)':<30} {long_name}")


def substituir_globalids(modelo: ifcopenshell.file, mapa: dict) -> dict:
    """
    Substitui os GlobalIds dos IfcSpace de acordo com o mapeamento fornecido.

    Args:
        modelo: Ficheiro IFC aberto com ifcopenshell
        mapa:   Dicionário {nome_espaço: novo_global_id}

    Returns:
        Dicionário com resultados: {nome: {"anterior": str, "novo": str, "sucesso": bool}}
    """
    resultados = {}
    espacos = modelo.by_type("IfcSpace")

    for espaco in espacos:
        nome = espaco.Name or ""
        if nome in mapa:
            global_id_anterior = espaco.GlobalId
            novo_global_id = mapa[nome]
            espaco.GlobalId = novo_global_id
            resultados[nome] = {
                "anterior": global_id_anterior,
                "novo": novo_global_id,
                "sucesso": True
            }

    # Identificar espaços do mapa que não foram encontrados no modelo
    for nome in mapa:
        if nome not in resultados:
            resultados[nome] = {
                "anterior": None,
                "novo": mapa[nome],
                "sucesso": False,
                "erro": f"Espaço '{nome}' não encontrado no modelo IFC"
            }

    return resultados


# ─── EXECUÇÃO PRINCIPAL ────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  VIVIENDA — Substituição de GlobalIds pós-exportação Revit")
    print("=" * 60)

    # 1. Verificar ficheiro de entrada
    if not os.path.exists(INPUT_IFC):
        print(f"\n[ERRO] Ficheiro não encontrado: {INPUT_IFC}")
        print("       Verifica o caminho em INPUT_IFC no início do script.")
        return

    print(f"\n[1/5] A abrir: {INPUT_IFC}")
    modelo = ifcopenshell.open(INPUT_IFC)
    schema = modelo.schema
    print(f"      Schema IFC: {schema}")

    # 2. Listar espaços antes da substituição
    print("\n[2/5] IfcSpace encontrados no modelo (antes da substituição):")
    listar_espacos(modelo)

    # 3. Criar backup
    print(f"\n[3/5] A criar backup de segurança...")
    backup_path = criar_backup(INPUT_IFC)
    print(f"      Backup criado: {backup_path}")

    # 4. Substituir GlobalIds
    print("\n[4/5] A substituir GlobalIds...")
    resultados = substituir_globalids(modelo, GLOBALID_MAP)

    print(f"\n      {'Espaço':<25} {'GlobalId anterior':<30} {'GlobalId novo':<20} {'Estado'}")
    print(f"      {'-'*25} {'-'*30} {'-'*20} {'-'*10}")
    todos_ok = True
    for nome, res in resultados.items():
        if res["sucesso"]:
            print(f"      {nome:<25} {res['anterior']:<30} {res['novo']:<20} ✓")
        else:
            print(f"      {nome:<25} {'—':<30} {res['novo']:<20} ✗ {res.get('erro','')}")
            todos_ok = False

    if not todos_ok:
        print("\n  [AVISO] Alguns espaços não foram encontrados.")
        print("          Verifica se os nomes em GLOBALID_MAP correspondem")
        print("          exactamente aos nomes definidos no Revit.")

    # 5. Guardar ficheiro de saída
    print(f"\n[5/5] A guardar: {OUTPUT_IFC}")
    modelo.write(OUTPUT_IFC)

    # 6. Verificação final
    print("\n─── Verificação final ───────────────────────────────────")
    modelo_verificacao = ifcopenshell.open(OUTPUT_IFC)
    listar_espacos(modelo_verificacao)

    print("\n" + "=" * 60)
    if todos_ok:
        print(f"  ✓ Concluído com sucesso.")
        print(f"  Ficheiro de saída: {OUTPUT_IFC}")
    else:
        print(f"  ⚠ Concluído com avisos — verifica os espaços assinalados.")
    print("=" * 60)


if __name__ == "__main__":
    main()
