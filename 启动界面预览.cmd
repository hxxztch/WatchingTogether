@echo off
setlocal
cd /d "%~dp0"
set "PREVIEW_PYTHON=%~dp0..\film-app\.venv-packaging\Scripts\pythonw.exe"
if exist "%~dp0.venv-packaging\Scripts\pythonw.exe" set "PREVIEW_PYTHON=%~dp0.venv-packaging\Scripts\pythonw.exe"
if not exist "%PREVIEW_PYTHON%" (
  echo Python environment not found. See UI-PREVIEW.txt for setup instructions.
  pause
  exit /b 1
)
start "" /d "%~dp0" "%PREVIEW_PYTHON%" "%~dp0client.py"
