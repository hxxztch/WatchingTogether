param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$DeltaZip,
    [Parameter(Mandatory=$true)][string]$FromVersion,
    [Parameter(Mandatory=$true)][string]$ToVersion,
    [int]$TargetProcessId = 0,
    [ValidateRange(1, 90)][int]$ExitWaitSeconds = 90,
    [switch]$NoRestart
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$installRoot = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$updateLog = Join-Path $installRoot 'crash.log'
function Write-UpdateLog([string]$message) {
    $line = '[{0}] INFO updater: {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    try { [IO.File]::AppendAllText($updateLog, $line + [Environment]::NewLine, [Text.Encoding]::UTF8) }
    catch { Write-Warning $line }
}
Write-UpdateLog "start from=$FromVersion to=$ToVersion process=$TargetProcessId"
$tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$tempRoot = Join-Path $tempParent ('wt-update-' + [guid]::NewGuid().ToString('N'))
if (-not ([IO.Path]::GetFullPath($tempRoot).StartsWith($tempParent + '\', [StringComparison]::OrdinalIgnoreCase))) {
    throw 'Invalid temporary directory'
}
New-Item -ItemType Directory -Path $tempRoot | Out-Null

function Safe-Target([string]$relative) {
    if ([string]::IsNullOrWhiteSpace($relative) -or $relative.StartsWith('/') -or
        $relative.Contains('\') -or $relative.Contains(':') -or
        @($relative.Split('/')) -contains '..' -or @($relative.Split('/')) -contains '.') {
        throw "Unsafe update path: $relative"
    }
    if ($relative -in @('config.json', 'crash.log', 'crash.log.1', 'crash.log.2', 'crash.log.3', 'fatal.log', 'fatal.log.1')) { throw "Protected file: $relative" }
    if ($relative.Split('/')[0] -ieq 'stickers') { throw "Protected user sticker path: $relative" }
    $target = [IO.Path]::GetFullPath((Join-Path $installRoot ($relative -replace '/', '\')))
    if (-not $target.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Update path escaped the installation: $relative"
    }
    return $target
}

function Check-Hash([string]$path, [string]$expected) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing file: $path" }
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
    if ($actual -ne $expected.ToLowerInvariant()) { throw "SHA256 mismatch: $path" }
}

function Wait-ClientExit([int]$processId, [int]$seconds) {
    if ($processId -eq $PID) { throw 'Cannot wait for the updater itself' }
    $client = $null
    try {
        $client = [Diagnostics.Process]::GetProcessById($processId)
    } catch [ArgumentException] {
        Write-UpdateLog "client already exited process=$processId"
        return
    }
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        Write-UpdateLog "waiting for client process=$processId timeout_seconds=$seconds"
        # Wait on this process object's exit state. A fresh PID lookup after
        # Wait-Process is neither an exit check nor safe against PID reuse.
        # Access/handle errors must reach the log instead of being silenced.
        if (-not $client.WaitForExit($seconds * 1000)) {
            throw "Client exit timed out after $seconds seconds; no application files changed"
        }
        Write-UpdateLog "client exit confirmed process=$processId elapsed_ms=$($watch.ElapsedMilliseconds)"
    } finally {
        $client.Dispose()
    }
}

$backup = Join-Path $tempRoot 'backup'
$stage = Join-Path $tempRoot 'stage'
New-Item -ItemType Directory -Path $backup, $stage | Out-Null
$committed = $false
$archive = $null
$phase = 'waiting_for_exit'
$clientExited = $TargetProcessId -le 0
try {
    if ($TargetProcessId -gt 0) {
        Wait-ClientExit $TargetProcessId $ExitWaitSeconds
        $clientExited = $true
    }
    $phase = 'reading_manifest'
    $archive = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($DeltaZip))
    $manifestEntry = $archive.GetEntry('manifest.json')
    if ($null -eq $manifestEntry) { throw 'Missing update manifest' }
    $reader = New-Object IO.StreamReader($manifestEntry.Open(), [Text.Encoding]::UTF8)
    try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($manifest.schema -ne 1 -or $manifest.from_version -ne $FromVersion -or
        $manifest.to_version -ne $ToVersion) { throw 'Update version mismatch' }
    Write-UpdateLog "manifest verified changed=$(@($manifest.files).Count) removed=$(@($manifest.removed).Count)"
    $affected = @($manifest.files) + @($manifest.removed)
    $seen = @{}
    $phase = 'validating_files'
    foreach ($item in $affected) {
        $relative = [string]$item.path
        if ($seen.ContainsKey($relative)) { throw "Duplicate update path: $relative" }
        $seen[$relative] = $true
        $target = Safe-Target $relative
        if ($null -eq $item.old_sha256 -or $item.old_sha256 -eq '') {
            if (Test-Path -LiteralPath $target) { throw "Unexpected existing file: $relative" }
        } else {
            Check-Hash $target ([string]$item.old_sha256)
            $saved = Join-Path $backup ($relative -replace '/', '\')
            New-Item -ItemType Directory -Force -Path (Split-Path $saved) | Out-Null
            Copy-Item -LiteralPath $target -Destination $saved
        }
    }
    $phase = 'staging_files'
    foreach ($item in $manifest.files) {
        $relative = [string]$item.path
        $entry = $archive.GetEntry('files/' + $relative)
        if ($null -eq $entry) { throw "Missing update file: $relative" }
        $staged = Join-Path $stage ($relative -replace '/', '\')
        New-Item -ItemType Directory -Force -Path (Split-Path $staged) | Out-Null
        $source = $entry.Open()
        $destination = [IO.File]::Create($staged)
        try { $source.CopyTo($destination) } finally { $destination.Dispose(); $source.Dispose() }
        Check-Hash $staged ([string]$item.sha256)
    }
    try {
        $phase = 'committing_files'
        foreach ($item in $manifest.files) {
            $target = Safe-Target ([string]$item.path)
            $staged = Join-Path $stage (([string]$item.path) -replace '/', '\')
            New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
            Copy-Item -LiteralPath $staged -Destination $target -Force
        }
        foreach ($item in $manifest.removed) {
            $target = Safe-Target ([string]$item.path)
            Remove-Item -LiteralPath $target -Force
        }
        $committed = $true
        Write-UpdateLog 'files committed'
    } finally {
        if (-not $committed) {
            foreach ($item in $affected) {
                $target = Safe-Target ([string]$item.path)
                $saved = Join-Path $backup (([string]$item.path) -replace '/', '\')
                if (Test-Path -LiteralPath $saved) {
                    Copy-Item -LiteralPath $saved -Destination $target -Force
                } elseif (Test-Path -LiteralPath $target -PathType Leaf) {
                    Remove-Item -LiteralPath $target -Force
                }
            }
        }
    }
    if (-not $NoRestart) {
        $phase = 'restarting'
        $newExe = Safe-Target ('超时空会夜机' + $ToVersion + '.exe')
        if (-not (Test-Path -LiteralPath $newExe -PathType Leaf)) { throw 'Updated EXE missing' }
        Start-Process -FilePath $newExe -WorkingDirectory $installRoot
    }
} catch {
    $detail = $_.Exception
    while ($null -ne $detail.InnerException) { $detail = $detail.InnerException }
    Write-UpdateLog "failed phase=$phase type=$($detail.GetType().Name) message=$($detail.Message)"
    if (-not $NoRestart) {
        $oldExe = Safe-Target ('超时空会夜机' + $FromVersion + '.exe')
        if ($clientExited -and -not $committed -and (Test-Path -LiteralPath $oldExe -PathType Leaf)) {
            Start-Process -FilePath $oldExe -WorkingDirectory $installRoot
        }
        $message = if ($committed) {
            '更新文件已安装，但新版本未能自动启动。请在原目录手动打开新版客户端。详细原因已记录在 crash.log。'
        } elseif (-not $clientExited) {
            '旧客户端未能正常退出，尚未修改程序文件。请关闭所有旧客户端窗口及后台进程后再升级；旧版本无法退出时，可改用完整便携包并保留 config.json 和 stickers。详细原因已记录在 crash.log。'
        } else {
            '更新未完成，已尝试恢复原程序文件。详细原因已记录在 crash.log；请检查日志或使用完整便携包升级，保留 config.json 和 stickers。'
        }
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            $message,
            '超时空会夜机') | Out-Null
    }
    throw
} finally {
    if ($null -ne $archive) { $archive.Dispose() }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
    Write-UpdateLog 'finished'
}
