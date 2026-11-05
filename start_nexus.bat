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
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  for %%P in ("%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
              "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
              "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
              "%LOCALAPPDATA%\Programs\Python\Python313\python.exe") do (
    if not defined PY if exist "%%~P" set "PY=%%~P"
  )
)
if not defined PY (
  echo [X] Python not found on PATH or in the default install location.
  echo     Install Python 3.10+ and retry.
  pause & exit /b 1
)
echo [*] Python: %PY%

REM ---------- FFmpeg (optional) ----------
ffmpeg -version >nul 2>nul && goto :ffmpeg_done
set "FFDIR="
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*") do (
  if not defined FFDIR for /d %%E in ("%%~D\ffmpeg-*-full_build") do (
    if exist "%%~E\bin\ffmpeg.exe" set "FFDIR=%%~E\bin"
  )
)
if not defined FFDIR if exist "%LOCALAPPDATA%\hermes\tools\ffmpeg-9.0.1-win32-x64\bin\ffmpeg.exe" (
  set "FFDIR=%LOCALAPPDATA%\hermes\tools\ffmpeg-9.0.1-win32-x64\bin"
)
if defined FFDIR (
  set "PATH=%FFDIR%;%PATH%"
  echo [+] FFmpeg found at %FFDIR% ^(added to PATH for this session^)
) else (
  echo [!] FFmpeg not found - video render will report tool_missing ^(not faked^).
)
:ffmpeg_done

"%PY%" -c "import fastapi, uvicorn, httpx, pydantic, psutil" >nul 2>nul
if errorlevel 1 (
  echo [*] Installing Python dependencies...
  "%PY%" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo [X] Dependency install failed. Run: python -m pip install -r requirements.txt
    pause & exit /b 1
  )
)

"%PY%" -c "import PIL" >nul 2>nul
if errorlevel 1 "%PY%" -m pip install --quiet Pillow

"%PY%" -c "import pyttsx3" >nul 2>nul
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
    ping -n 5 127.0.0.1 >nul 2>nul
    curl -s -m 3 http://127.0.0.1:11434/api/version >nul 2>nul
    if errorlevel 1 (
      echo [!] Ollama did not start. Open the Ollama app manually, or run: ollama serve
      echo     NEXUS still works using its labelled offline fallback.
    ) else (
      echo [+] Ollama is running.
    )
  )
  ollama list 2>nul | findstr /r /c:"qwen2.5-coder" /c:"qwen2.5:3b" /c:"gemma3:1b" /c:"ministral-3:3b" /c:"llama3.2" /c:"phi3:mini" /c:"gemma2:2b" >nul
  if errorlevel 1 (
    echo [!] No small model found. For full local AI run: ollama pull qwen2.5:3b
    echo     ^(approx 2 GB download; NEXUS works without it using its labelled fallback.^)
  ) else (
    echo [+] Small local model available - AI features use real local inference.
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
"%PY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8777
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo.
  echo [X] Server exited with code %EXITCODE%.
  pause
)
endlocal
