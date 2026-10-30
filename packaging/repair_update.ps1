param(
    [string]$ClientExe,
    [string]$DeltaZip,
    [switch]$NoRestart
)
$ErrorActionPreference = 'Stop'
$interactive = [string]::IsNullOrWhiteSpace($ClientExe) -or [string]::IsNullOrWhiteSpace($DeltaZip)
$installed = $false
$targetVersion = 'beta0.1.4'
# Digests of the actual published beta0.1.4 deltas, not user-provided manifests.
$officialDigests = @{
    'beta0.1.0' = '67d792eaa3a7388cf93c53a9891cfb56c08640105ed2476ab315093df6f066b6'
    'beta0.1.1' = '74996d91756dc4881c18d83fdc44d99a99744f418a24026150c55ff85925b80d'
    'beta0.1.2' = 'f171c701a838a740dcd85b5136084c74b133ed0e60ce19eee279757d234ea2f5'
    'beta0.1.3' = '57c9eb51eee5b05a837736114b95737f03d38d5e7f389501183477449f3a2bc3'
}

function Choose-File([string]$title, [string]$filter, [string]$directory) {
    $dialog = New-Object Windows.Forms.OpenFileDialog
    try {
        $dialog.Title = $title
        $dialog.Filter = $filter
        if (Test-Path -LiteralPath $directory -PathType Container) { $dialog.InitialDirectory = $directory }
        if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return $null }
        return $dialog.FileName
    } finally { $dialog.Dispose() }
}

try {
    if ($interactive) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show(
            '请先退出所有旧客户端，包括后台仍在运行的旧进程。接下来选择旧客户端 EXE 和已经下载的 beta0.1.4 差异包。昵称、登录信息及 stickers 不会被替换。',
            'beta0.1.4 更新修复助手') | Out-Null
    }
    if (-not $ClientExe) {
        $ClientExe = Choose-File '选择需要升级的旧客户端 EXE' '客户端 (*.exe)|*.exe' $PSScriptRoot
        if (-not $ClientExe) { exit 0 }
    }
    $ClientExe = (Resolve-Path -LiteralPath $ClientExe).Path
    $name = [IO.Path]::GetFileName($ClientExe)
    if ($name -notmatch '^超时空会夜机(?<version>beta\d+\.\d+\.\d+)\.exe$') {
        throw '所选文件不是带原始版本名的超时空会夜机客户端，请选择原来的 EXE。'
    }
    $fromVersion = $Matches['version']
    if (-not $officialDigests.ContainsKey($fromVersion)) { throw '此助手仅用于旧 beta 版本升级到 beta0.1.4。' }
    $installDir = [IO.Path]::GetDirectoryName($ClientExe)
    foreach ($process in [Diagnostics.Process]::GetProcessesByName([IO.Path]::GetFileNameWithoutExtension($ClientExe))) {
        try {
            if (-not $process.HasExited -and [string]::Equals(
                    $process.MainModule.FileName, $ClientExe, [StringComparison]::OrdinalIgnoreCase)) {
                throw '旧客户端仍在运行。请先关闭它；如果窗口已消失，请在任务管理器中结束该旧客户端，再重新运行助手。'
            }
        } finally { $process.Dispose() }
    }
    if (-not $DeltaZip) {
        $downloads = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads\WatchingTogether'
        $DeltaZip = Choose-File ('选择 ' + $fromVersion + '-to-beta0.1.4.delta.zip') '差异包 (*.delta.zip)|*.delta.zip' $downloads
        if (-not $DeltaZip) { exit 0 }
    }
    $DeltaZip = (Resolve-Path -LiteralPath $DeltaZip).Path
    $stream = [IO.File]::OpenRead($DeltaZip)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
    if ($actual -ne $officialDigests[$fromVersion]) {
        throw '差异包不匹配所选旧版本，或未通过正式发行包的 SHA256 校验。请重新选择正确的 beta0.1.4 差异包。'
    }
    if ($interactive) {
        $answer = [Windows.Forms.MessageBox]::Show(
            ('确认将 ' + $fromVersion + ' 升级到 beta0.1.4？' + [Environment]::NewLine + $installDir),
            '确认升级目录', [Windows.Forms.MessageBoxButtons]::OKCancel)
        if ($answer -ne [Windows.Forms.DialogResult]::OK) { exit 0 }
    }
    & (Join-Path $PSScriptRoot 'apply_update.ps1') -InstallDir $installDir -DeltaZip $DeltaZip `
        -FromVersion $fromVersion -ToVersion $targetVersion -NoRestart
    if (-not $?) { throw '差异安装未完成，请查看旧客户端目录的 crash.log。' }
    $installed = $true
    $newExe = Join-Path $installDir ('超时空会夜机' + $targetVersion + '.exe')
    if (-not (Test-Path -LiteralPath $newExe -PathType Leaf)) { throw '新版 EXE 未找到。' }
    if (-not $NoRestart) { Start-Process -FilePath $newExe -WorkingDirectory $installDir }
    Write-Output 'Repair update completed; personal configuration and stickers preserved.'
} catch {
    $prefix = if ($installed) { '更新文件已安装，但启动失败，请手动打开新版 EXE。' } else { '修复升级未完成。' }
    $message = $prefix + [Environment]::NewLine + $_.Exception.Message
    if ($interactive) { [Windows.Forms.MessageBox]::Show($message, '更新修复助手') | Out-Null }
    Write-Error $message -ErrorAction Continue
    exit 1
}
