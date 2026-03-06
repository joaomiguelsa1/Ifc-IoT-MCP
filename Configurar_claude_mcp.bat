@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM Script de Configuracao Automatica - Digital Twin BIM + IoT
REM Versao: 2.2 - COMPATIVEL COM CMD (sem Unicode)
REM Autor: Joao Rodrigues (FEUP)
REM Data: Novembro 2024
REM ============================================================

REM Definir cores (cores basicas CMD)
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "RESET=[0m"

REM Titulo
echo ============================================================
echo   Configuracao Automatica - Digital Twin BIM + IoT v2.2
echo ============================================================
echo.

REM ============================================================
REM PASSO 1: Verificar privilegios de Administrador
REM ============================================================
echo [Passo 1/6] Verificando privilegios...

net session >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%[OK] Executando como Administrador%RESET%
) else (
    echo %RED%[ERRO] Necessita privilegios de Administrador!%RESET%
    echo.
    echo Execute este script com botao direito e "Executar como Administrador"
    echo.
    pause
    exit /b 1
)
echo.

REM ============================================================
REM PASSO 2: Localizar Python
REM ============================================================
echo [Passo 2/6] Localizando Python...

set "PYTHON_CMD="

REM Tentar encontrar Python no PATH
where python >nul 2>&1
if %errorLevel% == 0 (
    for /f "delims=" %%i in ('where python') do set "PYTHON_CMD=%%i"
    echo %GREEN%[OK] Python encontrado no PATH%RESET%
    echo      Caminho: !PYTHON_CMD!
    goto :VerifyPythonVersion
)

REM Procurar em localizacoes comuns (Python 3.13)
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    echo %GREEN%[OK] Python 3.13 encontrado%RESET%
    goto :VerifyPythonVersion
)

REM Procurar em localizacoes comuns (Python 3.12)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    echo %GREEN%[OK] Python 3.12 encontrado%RESET%
    goto :VerifyPythonVersion
)

REM Python nao encontrado
echo %RED%[ERRO] Python nao encontrado!%RESET%
echo.
echo Por favor, instale Python 3.12 ou 3.13 de:
echo https://www.python.org/downloads/
echo.
echo IMPORTANTE: Durante instalacao, marque "Add Python to PATH"
echo.
pause
exit /b 1

:VerifyPythonVersion
REM Verificar versao Python
for /f "tokens=2" %%v in ('"%PYTHON_CMD%" --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo      Versao: %PYTHON_VERSION%
echo.

REM ============================================================
REM PASSO 3: Localizar Servidor MCP
REM ============================================================
echo [Passo 3/6] Localizando servidor MCP...

set "MCP_SERVER="

REM Tentar diretorio atual
if exist "%~dp0..\ifc_iot_server.py" (
    set "MCP_SERVER=%~dp0..\ifc_iot_server.py"
    echo %GREEN%[OK] Servidor encontrado (diretorio pai)%RESET%
    goto :FoundMCPServer
)

REM Tentar Desktop do utilizador
set "DESKTOP_PATH=%USERPROFILE%\Desktop\ifc-iot-mcp\ifc_iot_server.py"
if exist "!DESKTOP_PATH!" (
    set "MCP_SERVER=!DESKTOP_PATH!"
    echo %GREEN%[OK] Servidor encontrado (Desktop)%RESET%
    goto :FoundMCPServer
)

REM Tentar diretorio atual
if exist "%CD%\ifc_iot_server.py" (
    set "MCP_SERVER=%CD%\ifc_iot_server.py"
    echo %GREEN%[OK] Servidor encontrado (diretorio atual)%RESET%
    goto :FoundMCPServer
)

REM Servidor nao encontrado - pedir caminho
echo %YELLOW%[AVISO] Servidor MCP nao encontrado automaticamente%RESET%
echo.
set /p "MCP_SERVER=Digite o caminho completo para ifc_iot_server.py: "
if not exist "!MCP_SERVER!" (
    echo %RED%[ERRO] Ficheiro nao encontrado: !MCP_SERVER!%RESET%
    pause
    exit /b 1
)

:FoundMCPServer
echo      Caminho: !MCP_SERVER!
echo.

REM ============================================================
REM PASSO 4: Instalar Dependencias Python
REM ============================================================
echo [Passo 4/6] Instalando dependencias Python...
echo      Isto pode demorar alguns minutos...
echo.

REM Instalar ifcopenshell
echo      [1/5] ifcopenshell...
"%PYTHON_CMD%" -m pip install ifcopenshell --break-system-packages --quiet >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%      [OK] ifcopenshell instalado%RESET%
) else (
    echo %YELLOW%      [AVISO] ifcopenshell pode ja estar instalado%RESET%
)

REM Instalar mcp
echo      [2/5] mcp...
"%PYTHON_CMD%" -m pip install "mcp>=1.0.0" --break-system-packages --quiet >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%      [OK] mcp instalado%RESET%
) else (
    echo %YELLOW%      [AVISO] mcp pode ja estar instalado%RESET%
)

REM Instalar flask
echo      [3/5] flask...
"%PYTHON_CMD%" -m pip install flask --break-system-packages --quiet >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%      [OK] flask instalado%RESET%
) else (
    echo %YELLOW%      [AVISO] flask pode ja estar instalado%RESET%
)

REM Instalar flask-cors
echo      [4/5] flask-cors...
"%PYTHON_CMD%" -m pip install flask-cors --break-system-packages --quiet >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%      [OK] flask-cors instalado%RESET%
) else (
    echo %YELLOW%      [AVISO] flask-cors pode ja estar instalado%RESET%
)

REM Instalar python-dotenv
echo      [5/5] python-dotenv...
"%PYTHON_CMD%" -m pip install python-dotenv --break-system-packages --quiet >nul 2>&1
if %errorLevel% == 0 (
    echo %GREEN%      [OK] python-dotenv instalado%RESET%
) else (
    echo %YELLOW%      [AVISO] python-dotenv pode ja estar instalado%RESET%
)

echo.
echo %GREEN%[OK] Todas as dependencias instaladas/verificadas%RESET%
echo.

REM ============================================================
REM PASSO 5: Configurar Claude Desktop
REM ============================================================
echo [Passo 5/6] Configurando Claude Desktop...

set "CLAUDE_DIR=%APPDATA%\Claude"
set "CONFIG_FILE=%CLAUDE_DIR%\claude_desktop_config.json"

REM Criar diretorio se nao existir
if not exist "%CLAUDE_DIR%" (
    mkdir "%CLAUDE_DIR%"
    echo      [+] Diretorio criado: %CLAUDE_DIR%
)

REM Fazer backup se config ja existir
if exist "%CONFIG_FILE%" (
    copy "%CONFIG_FILE%" "%CONFIG_FILE%.backup" >nul
    echo %YELLOW%      [Backup] Configuracao anterior guardada como .backup%RESET%
)

REM Converter caminhos para formato JSON (\ -> \\)
set "PYTHON_JSON=!PYTHON_CMD:\=\\!"
set "MCP_JSON=!MCP_SERVER:\=\\!"

REM Criar ficheiro de configuracao
(
echo {
echo   "mcpServers": {
echo     "ifc-iot-mapper": {
echo       "command": "!PYTHON_JSON!",
echo       "args": [
echo         "!MCP_JSON!"
echo       ]
echo     }
echo   }
echo }
) > "%CONFIG_FILE%"

echo %GREEN%[OK] Configuracao criada%RESET%
echo      Ficheiro: %CONFIG_FILE%
echo.

REM ============================================================
REM PASSO 6: Validar Configuracao
REM ============================================================
echo [Passo 6/6] Validando configuracao...

REM Validar sintaxe JSON
"%PYTHON_CMD%" -c "import json; json.load(open(r'%CONFIG_FILE%'))" 2>nul
if %errorLevel% == 0 (
    echo %GREEN%[OK] Sintaxe JSON valida%RESET%
) else (
    echo %RED%[ERRO] Ficheiro JSON tem erros de sintaxe!%RESET%
    echo      Verifique: %CONFIG_FILE%
    pause
    exit /b 1
)

REM Testar importacao do servidor MCP
"%PYTHON_CMD%" -c "import sys; sys.path.append(r'%~dp0..'); exec(open(r'!MCP_SERVER!').read(), {'__name__': '__test__'})" 2>nul
if %errorLevel% == 0 (
    echo %GREEN%[OK] Servidor MCP importavel%RESET%
) else (
    echo %YELLOW%[AVISO] Nao foi possivel testar servidor MCP%RESET%
    echo          Isto pode ser normal se houver dependencias em falta
)
echo.

REM ============================================================
REM RESUMO FINAL
REM ============================================================
echo ============================================================
echo   CONFIGURACAO CONCLUIDA COM SUCESSO!
echo ============================================================
echo.
echo Resumo da configuracao:
echo   - Python:    !PYTHON_CMD!
echo   - Servidor:  !MCP_SERVER!
echo   - Config:    %CONFIG_FILE%
echo.
echo Proximos passos:
echo.
echo   1. REINICIAR Claude Desktop completamente
echo      - Fechar TODAS as janelas do Claude
echo      - Fechar icone no system tray (se existir)
echo      - Reabrir Claude Desktop
echo.
echo   2. Verificar conexao MCP no Claude
echo      - Procurar icone de martelo ou "MCP server connected"
echo.
echo   3. Iniciar backend Flask (separadamente):
echo      python backend_v2_2_historico.py
echo.
echo   4. Abrir interface web:
echo      http://localhost:5000/static/index_v2_1_multiprojeto.html
echo.
echo ============================================================
pause
