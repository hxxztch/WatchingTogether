@echo off
chcp 65001
cd /d "%~dp0"
start /min "" "%~dp0超时空会夜机_服务器.exe"
if exist "%~dp0ngrok.exe" (
    "%~dp0ngrok.exe" http 9877
    taskkill /f /im 超时空会夜机_服务器.exe
) else (
    echo Server started on port 9877
    echo LAN: ws://localhost:9877
    pause
)