$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot '..\tools\cloudflared.exe'
$directory = Split-Path $target
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$expected = '4d2490e74082c5d48dbfedaf92576fa5bd1702379ab88eb7faa0cfbe8dc891b6'
if (!(Test-Path -LiteralPath $target) -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expected) {
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.1/cloudflared-windows-amd64.exe' -OutFile ($target + '.download')
    if ((Get-FileHash -LiteralPath ($target + '.download') -Algorithm SHA256).Hash -ne $expected) { throw 'cloudflared SHA256 mismatch' }
    Move-Item -LiteralPath ($target + '.download') -Destination $target -Force
}
Write-Output 'cloudflared 2026.10.1 verified.'
