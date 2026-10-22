@echo off
setlocal
cd /d "%~dp0"
set "CONDA_BAT=%~dp0..\Anaconda\condabin\conda.bat"
if not exist "%CONDA_BAT%" (
  echo Conda installation not found: "%CONDA_BAT%"
  pause
  exit /b 1
)
call "%CONDA_BAT%" activate watchingtogether-beta010
if errorlevel 1 (
  echo Failed to activate Conda environment watchingtogether-beta010.
  pause
  exit /b 1
)
if not exist "%CONDA_PREFIX%\pythonw.exe" (
  echo Python environment not found: "%CONDA_PREFIX%"
  pause
  exit /b 1
)
start "" /d "%~dp0" "%CONDA_PREFIX%\pythonw.exe" "%~dp0client.py"
