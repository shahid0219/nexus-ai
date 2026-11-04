@echo off
setlocal EnableExtensions
title NEXUS AI
cd /d "%~dp0"

echo ============================================
echo   NEXUS AI - local-first growth platform
echo ============================================
echo.

if not exist "data" mkdir "data"
if not exist "data\artifacts" mkdir "data\artifacts"
if not exist "data\reports" mkdir "data\reports"

REM ---------- Python ----------
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python not found on PATH. Install Python 3.10+ and retry.
  pause & exit /b 1
)

python -c "import fastapi, uvicorn, httpx, pydantic, psutil" >nul 2>nul
if errorlevel 1 (
  echo [*] Installing Python dependencies...
  python -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo [X] Dependency install failed. Run: python -m pip install -r requirements.txt
    pause & exit /b 1
  )
)

python -c "import PIL" >nul 2>nul
if errorlevel 1 python -m pip install --quiet Pillow

python -c "import pyttsx3" >nul 2>nul
if errorlevel 1 echo [!] pyttsx3 missing - voiceover will report unavailable (not faked).

REM ---------- Frontend ----------
if not exist "frontend\dist\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [!] npm not found - the API will run, dashboard will not be served.
  ) else (
    echo [*] Building dashboard ^(first run only^)...
    pushd frontend
    if not exist node_modules call npm install --no-fund --no-audit
    call npm run build
    popd
  )
)

REM ---------- Ollama (optional, never required) ----------
where ollama >nul 2>nul
if not errorlevel 1 (
  curl -s -m 2 http://127.0.0.1:11434/api/version >nul 2>nul
  if errorlevel 1 (
    echo [*] Starting Ollama in the background...
    start "Ollama" /min cmd /c "ollama serve"
    timeout /t 3 /nobreak >nul
  )
  ollama list 2>nul | findstr /r /c:"qwen2.5:3b" /c:"llama3.2" >nul
  if errorlevel 1 (
    echo [!] No small model found. For full local AI run: ollama pull qwen2.5:3b
    echo     NEXUS works without it using its labelled offline fallback.
  )
)

REM ---------- Port check ----------
netstat -ano | findstr /r /c:":8777 .*LISTENING" >nul
if not errorlevel 1 (
  echo [X] Port 8777 is already in use. Run stop_nexus.bat first.
  pause & exit /b 1
)

echo.
echo [*] Starting NEXUS AI on http://127.0.0.1:8777
echo     Press Ctrl+C in this window to stop.
echo.

start "" "http://127.0.0.1:8777"

set PYTHONPATH=%~dp0backend
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo [X] Server exited with code %EXITCODE%.
  pause
)
endlocal
