$ErrorActionPreference = 'Stop'
$root = Join-Path (Split-Path $PSScriptRoot) 'tools\opus'
$package = 'libopus-1.6.1-h6a83c73_1'
$sha = '0ca8a5f9c6505344d3c57068b50d2cfffe497e3ce1aa697deb46d8ab502d3cfa'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$archive = Join-Path $root "$package.conda"
Invoke-WebRequest -UseBasicParsing "https://conda.anaconda.org/conda-forge/win-64/$package.conda" -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $sha) { throw 'Opus checksum mismatch' }
tar.exe -xf $archive -C $root "pkg-$package.tar.zst" "info-$package.tar.zst"
if ($LASTEXITCODE) { throw 'Could not extract Opus package' }
tar.exe -xf (Join-Path $root "pkg-$package.tar.zst") -C $root Library/bin/opus.dll
if ($LASTEXITCODE) { throw 'Could not extract Opus DLL' }
tar.exe -xf (Join-Path $root "info-$package.tar.zst") -C $root info/licenses
if ($LASTEXITCODE) { throw 'Could not extract Opus license' }
