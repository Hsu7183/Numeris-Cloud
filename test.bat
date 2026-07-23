@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Numeris] Run setup.bat first.
  exit /b 1
)
echo [1/4] Ruff
".venv\Scripts\python.exe" -m ruff check app tests scripts
if errorlevel 1 exit /b 1
echo [2/4] Mypy core modules
".venv\Scripts\python.exe" -m mypy
if errorlevel 1 exit /b 1
echo [3/4] Pytest
set "PYTHONPATH=%CD%\tests"
".venv\Scripts\python.exe" -m pytest
if errorlevel 1 exit /b 1
echo [4/4] Pytest coverage for core algorithms
".venv\Scripts\python.exe" -m pytest tests\unit\test_analytics.py tests\unit\test_coverage_fast.py --cov=app.services.analytics --cov=app.services.generation.generators --cov-report=term-missing --cov-report=html:reports\build\coverage
if errorlevel 1 exit /b 1
echo [Numeris] All tests completed.
endlocal
