@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" evaluate_logicai.py
pause
