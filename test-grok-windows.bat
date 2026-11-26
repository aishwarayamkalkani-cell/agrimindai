@echo off
cd /d "%~dp0backend"
if not exist .venv (echo Run setup-windows.bat first. & pause & exit /b 1)
call .venv\Scripts\activate.bat
echo === Automated tests (offline, mocked xAI) ===
python -m pytest -q tests
echo.
echo === Genuine Grok integration check (real, billed xAI requests - about 12 short calls) ===
python scripts\grok_integration_check.py
echo.
echo Report written to backend\grok_integration_report.md
pause
