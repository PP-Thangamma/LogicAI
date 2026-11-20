@echo off
cd /d "%~dp0"
set DATABASE_PATH=%~dp0demo_logicai.db
if not defined SECRET_KEY set SECRET_KEY=local-demo-only-change-before-deployment
if not exist ".venv\Scripts\python.exe" (
  echo Create the virtual environment first: py -m venv .venv
  pause
  exit /b 1
)
if not exist "demo_logicai.db" (
  echo Creating separate demo database...
  ".venv\Scripts\python.exe" seed_demo.py
  if errorlevel 1 pause & exit /b 1
)
".venv\Scripts\python.exe" app.py
pause
