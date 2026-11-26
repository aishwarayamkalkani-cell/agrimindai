@echo off
setlocal
cd /d "%~dp0backend"
echo === AgriMind AI setup ===
where python >nul 2>nul || (echo Python 3.10-3.13 is required: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
  echo NVIDIA GPU detected - installing CUDA build of PyTorch...
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 || pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
) else (
  echo No NVIDIA GPU detected - installing CPU build of PyTorch...
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
)
pip install -r requirements-full.txt || (pause & exit /b 1)
if not exist .env copy .env.example .env >nul
echo Re-training the crop recommendation model for your scikit-learn version...
python training\train_crop.py
echo.
echo Setup complete.
echo  1. Put your xAI key in backend\.env as XAI_API_KEY=... (or add it later in Admin - Model configuration)
echo  2. Optional: run test-grok-windows.bat to check the real Grok connection
echo  3. Run start-windows.bat
pause
