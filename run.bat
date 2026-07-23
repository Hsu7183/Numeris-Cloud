@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Run setup.bat first.
  exit /b 1
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8767 .*LISTENING"') do (
  echo [Numeris] Port 8767 is already used by process %%P.
  exit /b 1
)
if not exist "logs" mkdir "logs"
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8767/'"
echo [Numeris] Starting at http://127.0.0.1:8767/
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8767
endlocal
