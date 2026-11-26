@echo off
cd /d "%~dp0backend"
if not exist .venv (echo Run setup-windows.bat first. & pause & exit /b 1)
call .venv\Scripts\activate.bat
echo Starting AgriMind AI at http://127.0.0.1:8000  (first start downloads the embedding model, ~470 MB)
start "" cmd /c "timeout /t 12 >nul & start http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
