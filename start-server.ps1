# 超时空会夜机 - 服务器启动脚本
# 在 PowerShell 中运行: .\start-server.ps1

 = "E:\Study\code\film-app"
Set-Location 

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Sync Movie Server Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Starting WebSocket server..." -ForegroundColor Yellow
 = Start-Job -Name "SyncServer" -ScriptBlock {
    Set-Location "E:\Study\code\film-app"
    python server.py
}
Start-Sleep -Seconds 1
Write-Host "      OK (server running in background)" -ForegroundColor Green
Start-Sleep -Seconds 2

Write-Host "[2/3] Looking for ngrok..." -ForegroundColor Yellow
 = @(
    "E:\Study\code\ngrok\ngrok.exe",
    "\ngrok.exe",
    "C:\Users\Administrator\AppData\Local\ngrok\ngrok.exe",
    "C:\Users\Administrator\ngrok.exe"
)
 = 
foreach ( in ) {
    if (Test-Path ) {  = ; break }
}

if (-not ) {
    Write-Host "      ngrok not found." -ForegroundColor Red
    Write-Host "      Please run manually: ngrok http 9877" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

Write-Host "[3/3] Starting ngrok tunnel..." -ForegroundColor Yellow
Write-Host ""
Write-Host "ngrok: " -ForegroundColor Gray
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Find the line:" -ForegroundColor White
Write-Host " Forwarding  https://xxx.ngrok-free.dev" -ForegroundColor Green
Write-Host ""
Write-Host " Send https://xxx.ngrok-free.dev" -ForegroundColor White
Write-Host " to your friend as server address" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Close this window to stop ngrok + server" -ForegroundColor Gray
Write-Host ""

try {
    &  http 9877
}
finally {
    Write-Host "" -ForegroundColor Yellow
    Write-Host "Stopping server..." -ForegroundColor Yellow
    Stop-Job  -ErrorAction SilentlyContinue
    Remove-Job  -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Green
}