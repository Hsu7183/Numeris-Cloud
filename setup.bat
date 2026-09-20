@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [Numeris] Checking Python...
set "PYTHON_CMD="
py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.13"
if defined PYTHON_CMD goto python_found
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if defined PYTHON_CMD goto python_found
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if defined PYTHON_CMD goto python_found
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if defined PYTHON_CMD goto python_found
python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python3"
if defined PYTHON_CMD goto python_found

for %%P in (
  "%LocalAppData%\Programs\Python\Python314\python.exe"
  "%LocalAppData%\Programs\Python\Python313\python.exe"
  "%LocalAppData%\Programs\Python\Python312\python.exe"
  "%ProgramFiles%\Python314\python.exe"
  "%ProgramFiles%\Python313\python.exe"
  "%ProgramFiles%\Python312\python.exe"
) do (
  if not defined PYTHON_CMD if exist "%%~P" set PYTHON_CMD="%%~P"
)
if not defined PYTHON_CMD (
  goto no_python
)

:python_found
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo [Numeris] The copied virtual environment belongs to another computer.
    echo [Numeris] Removing the invalid environment so it can be rebuilt locally...
    rmdir /s /q ".venv"
    if exist ".venv" goto failed
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Creating the project virtual environment...
  %PYTHON_CMD% -m venv ".venv"
  if errorlevel 1 goto :failed
)
echo [Numeris] Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 goto :failed
set "MYPY_USE_MYPYC=0"
".venv\Scripts\python.exe" -m pip install --force-reinstall --no-binary mypy mypy==1.15.0
if errorlevel 1 goto :failed
echo [Numeris] Installing Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 echo [Numeris] Browser installation failed; retry later with playwright install chromium.
echo [Numeris] Applying database migrations...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 goto :failed
echo [Numeris] Loading games, presets, and deterministic fixtures...
".venv\Scripts\python.exe" -m scripts.init_data --fixture --draws 60
if errorlevel 1 goto :failed
echo [Numeris] Running the database health check...
".venv\Scripts\python.exe" -c "from app.core.database import database_status; print(database_status())"
if errorlevel 1 goto :failed
echo [Numeris] Setup completed.
endlocal
exit /b 0

:no_python
echo [Numeris] Python 3.12 or newer was not found.
echo [Numeris] Install 64-bit Python from https://www.python.org/downloads/windows/
echo [Numeris] Then run setup.bat again.
endlocal
exit /b 1

:failed
echo [Numeris] Setup failed. Review the message above.
endlocal
exit /b 1
