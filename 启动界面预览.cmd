@echo off
setlocal
cd /d "%~dp0"
set "PREVIEW_PYTHON=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PREVIEW_PYTHON%" goto launch
set "PREVIEW_PYTHON=%~dp0.venv-packaging\Scripts\pythonw.exe"
if exist "%PREVIEW_PYTHON%" goto launch
set "PREVIEW_PYTHON=%~dp0..\film-app\.venv-packaging\Scripts\pythonw.exe"
if exist "%PREVIEW_PYTHON%" goto launch
echo Preview Python environment not found. Run client.py in your development environment.
pause
exit /b 1
:launch
start "" /d "%~dp0" "%PREVIEW_PYTHON%" "%~dp0client.py"
