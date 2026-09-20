@echo off
setlocal
cd /d "%~dp0"
rem Double-click this file to launch the Daily 539 statistics page.
set "NUMERIS_URL=http://127.0.0.1:8767/539"
set "NUMERIS_REFRESH_ONLY="

if /i "%~1"=="--open-only" goto open_browser
if /i "%~1"=="--refresh-only" set "NUMERIS_REFRESH_ONLY=1"

set "NUMERIS_SETUP_REQUIRED="
if not exist ".venv\Scripts\python.exe" set "NUMERIS_SETUP_REQUIRED=1"
if not defined NUMERIS_SETUP_REQUIRED (
  ".venv\Scripts\python.exe" -c "import fastapi, sqlalchemy, uvicorn; import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
  if errorlevel 1 set "NUMERIS_SETUP_REQUIRED=1"
)
if defined NUMERIS_SETUP_REQUIRED (
  echo [Numeris] The local Python environment is missing or belongs to another computer.
  echo [Numeris] Rebuilding it for this computer...
  call setup.bat
  if errorlevel 1 (
    echo [Numeris] Setup could not be completed.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "from app.main import app" >nul 2>&1
if errorlevel 1 (
  echo [Numeris] The application files or dependencies are incomplete.
  echo [Numeris] Run setup.bat and review its error message.
  pause
  exit /b 1
)

if not exist "logs" mkdir "logs"

set "NUMERIS_PORT_PID="
set "NUMERIS_ALREADY_RUNNING="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8767 .*LISTENING"') do set "NUMERIS_PORT_PID=%%P"

if defined NUMERIS_PORT_PID (
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8767/api/health' -TimeoutSec 3; if ($r.status -eq 'ok' -and $r.service -like 'Numeris*') { exit 0 } else { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    set "NUMERIS_ALREADY_RUNNING=1"
  ) else (
    echo [Numeris] Port 8767 is used by another program, PID %NUMERIS_PORT_PID%.
    echo Close that program and run this file again.
    pause
    exit /b 1
  )
)

echo [Numeris] 1/3 Updating official draw data...
echo [Numeris] This can take a moment. Please keep this window open.
".venv\Scripts\python.exe" -m scripts.startup_refresh
if errorlevel 1 (
  echo [Numeris] Update was incomplete. Starting with the last verified data.
)

if defined NUMERIS_REFRESH_ONLY (
  echo [Numeris] Refresh-only check completed.
  endlocal
  exit /b 0
)

if defined NUMERIS_ALREADY_RUNNING (
  echo [Numeris] 2/3 Service is already running.
  echo [Numeris] 3/3 Opening the refreshed full-screen dashboard...
  call :open_browser
  endlocal
  exit /b 0
)

echo [Numeris] 2/3 Starting the local service...
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; & '%~f0' '--open-only'"
echo [Numeris] 3/3 Opening Daily 539 statistics...
echo [Numeris] Close this window to stop the service.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8767
endlocal
exit /b

:open_browser
set "NUMERIS_BROWSER="
set "NUMERIS_BROWSER_PROFILE=%~dp0logs\chrome-dashboard-profile"
if not exist "%~dp0logs" mkdir "%~dp0logs"
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
  start "" "%NUMERIS_BROWSER%" --user-data-dir="%NUMERIS_BROWSER_PROFILE%" --no-first-run --disable-session-crashed-bubble --start-maximized --start-fullscreen --app=%NUMERIS_URL%
) else (
  start "" "%NUMERIS_URL%"
)
exit /b
