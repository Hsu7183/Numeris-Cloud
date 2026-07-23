@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Setup is incomplete. Run setup.bat first.
  pause
  exit /b 1
)

if not exist "logs" mkdir "logs"

set "NUMERIS_PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8767 .*LISTENING"') do set "NUMERIS_PORT_PID=%%P"

if defined NUMERIS_PORT_PID (
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8767/api/health' -TimeoutSec 3; if ($r.status -eq 'ok' -and $r.service -like 'Numeris*') { exit 0 } else { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    echo [Numeris] Already running. Opening the browser...
    start "" "http://127.0.0.1:8767/"
    powershell -NoProfile -Command "Start-Sleep -Milliseconds 600"
    exit /b 0
  )
  echo [Numeris] Port 8767 is used by another program, PID %NUMERIS_PORT_PID%.
  echo Close that program and run this file again.
  pause
  exit /b 1
)

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8767/'"
echo [Numeris] Starting http://127.0.0.1:8767/
echo [Numeris] Close this window to stop the service.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8767
endlocal
