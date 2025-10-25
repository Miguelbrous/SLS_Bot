@echo off
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%SCRIPT_DIR%"

if not exist venv (
  echo [setup] Creando entorno virtual en %SCRIPT_DIR%venv
  py -3 -m venv venv
)

call venv\Scripts\activate

set "REQ_FILE=%SCRIPT_DIR%requirements-dev.txt"
if not exist "%REQ_FILE%" (
  echo [error] No se encontro %REQ_FILE%
  exit /b 1
)

if not exist venv\.deps_installed (
  echo [setup] Instalando dependencias desde %REQ_FILE%
  python -m pip install --upgrade pip
  pip install -r "%REQ_FILE%"
  if errorlevel 1 (
    echo [error] Fallo la instalacion de dependencias
    exit /b 1
  )
  echo ok> venv\.deps_installed
)

set "PYTHONPATH=%REPO_ROOT%"
if not defined SLSBOT_CONFIG set "SLSBOT_CONFIG=%REPO_ROOT%\config\config.json"
if not defined PORT set "PORT=8080"

echo [run] Ejecutando API en http://127.0.0.1:%PORT%
python -m uvicorn sls_bot.app:app --host 127.0.0.1 --port %PORT% --log-level info
