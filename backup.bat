@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Run setup.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.backup
endlocal
