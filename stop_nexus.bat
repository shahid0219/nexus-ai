@echo off
setlocal EnableExtensions
title NEXUS AI - stop

echo Stopping NEXUS AI on port 8777...

set FOUND=0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8777 .*LISTENING"') do (
  echo   terminating PID %%P
  taskkill /PID %%P /F >nul 2>nul
  set FOUND=1
)

if "%FOUND%"=="0" (
  echo   nothing was listening on 8777.
) else (
  echo [OK] NEXUS AI stopped.
)

echo.
echo Note: Ollama is left running (it is a shared system service).
echo       Stop it manually with: taskkill /IM ollama.exe /F
ping -n 2 127.0.0.1 >nul 2>nul
endlocal
