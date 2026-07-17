@echo off
chcp 65001 >nul
title Sync Server

cd /d "E:\Study\code\film-app"

echo ========================================
echo   Sync Movie Server Launcher
echo ========================================
echo.

echo [1/3] Starting WebSocket server...
start /min "SyncServer" cmd /c "python server.py"
if %errorlevel% neq 0 (
    echo [WARNING] Make sure Python is installed
)
echo       OK (server running in background)
echo.

timeout /t 2 /nobreak >nul

echo [2/3] Looking for ngrok...
set NGROK_PATH=
if exist "E:\Study\code\ngrok\ngrok.exe" set NGROK_PATH=E:\Study\code\ngrok\ngrok.exe
if exist "%~dp0ngrok.exe" set NGROK_PATH=%~dp0ngrok.exe
if exist "%LOCALAPPDATA%\ngrok\ngrok.exe" set NGROK_PATH=%LOCALAPPDATA%\ngrok\ngrok.exe
if exist "%USERPROFILE%\ngrok.exe" set NGROK_PATH=%USERPROFILE%\ngrok.exe

if "%NGROK_PATH%"=="" (
    echo       ngrok not found.
    echo       Please run manually: ngrok http 9877
    echo.
    echo       Or download from: https://ngrok.com/download
    pause
    exit /b 0
)

echo [3/3] Starting ngrok tunnel...
echo.
echo ngrok: %NGROK_PATH%
echo.
echo ========================================
echo  Find the line:
echo  Forwarding  https://xxx.ngrok-free.dev
echo.
echo  Send https://xxx.ngrok-free.dev
echo  to your friend as server address
echo ========================================
echo.
"%NGROK_PATH%" http 9877

echo Stopping server...
taskkill /f /fi "WINDOWTITLE eq SyncServer" >nul 2>nul
echo Done.
pause