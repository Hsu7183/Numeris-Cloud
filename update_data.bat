@echo off
setlocal
cd /d "%~dp0"
set "SCOPE=%~1"
if "%SCOPE%"=="" set "SCOPE=all"
if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Run setup.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" -c "from app.core.database import SessionLocal; from app.services.data_sources.official import create_update_job,run_update_job; db=SessionLocal(); r=create_update_job(db,'%SCOPE%'); db.close(); print(r); run_update_job(r['job_uuid'])"
endlocal
