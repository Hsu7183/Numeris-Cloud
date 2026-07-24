@echo off
setlocal
cd /d "%~dp0"
set "NUMERIS_URL=http://127.0.0.1:8767/"

if /i "%~1"=="--open-only" goto open_browser

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
    echo [Numeris] Already running. Opening the full-screen dashboard...
    call :open_browser
    exit /b 0
  )
  echo [Numeris] Port 8767 is used by another program, PID %NUMERIS_PORT_PID%.
  echo Close that program and run this file again.
  pause
  exit /b 1
)

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; & '%~f0' '--open-only'"
echo [Numeris] Starting http://127.0.0.1:8767/
echo [Numeris] Close this window to stop the service.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8767
endlocal
exit /b

:open_browser
set "NUMERIS_BROWSER="
for %%B in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
) do (
  if not defined NUMERIS_BROWSER if exist "%%~B" set "NUMERIS_BROWSER=%%~B"
)
if defined NUMERIS_BROWSER (
  start "" "%NUMERIS_BROWSER%" --new-window --start-maximized --start-fullscreen --app=%NUMERIS_URL%
) else (
  start "" "%NUMERIS_URL%"
)
exit /b
