param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$setup = Join-Path $repo "dist\ConfluenceExportDesktopSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    throw "Installer not found: $setup"
}

$installDir = Join-Path ([System.IO.Path]::GetTempPath()) ("confluence-export-desktop-install-smoke-" + [guid]::NewGuid().ToString("N"))
$result = [ordered]@{
    installer = $setup
    install_dir = $installDir
    install_exit_code = $null
    app_launch = $null
    uninstall_exit_code = $null
    ok = $false
}

try {
    $install = Start-Process -FilePath $setup -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=$installDir"
    ) -Wait -PassThru
    $result.install_exit_code = $install.ExitCode
    if ($install.ExitCode -ne 0) {
        throw "Installer exited with code $($install.ExitCode)"
    }

    $exe = Join-Path $installDir "confluence-export-desktop.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Installed executable missing: $exe"
    }

    $oldDisableTray = [Environment]::GetEnvironmentVariable("CONFLUENCE_EXPORT_DISABLE_TRAY", "Process")
    [Environment]::SetEnvironmentVariable("CONFLUENCE_EXPORT_DISABLE_TRAY", "1", "Process")
    try {
        $proc = Start-Process -FilePath $exe -WorkingDirectory $installDir -PassThru
        Start-Sleep -Seconds 3
        $running = -not $proc.HasExited
        $result.app_launch = [ordered]@{
            ok = $running
            running_after_seconds = 3
            pid = $proc.Id
            path = $exe
        }
        if ($running) {
            Stop-Process -Id $proc.Id -Force
        }
    }
    finally {
        [Environment]::SetEnvironmentVariable("CONFLUENCE_EXPORT_DISABLE_TRAY", $oldDisableTray, "Process")
    }

    $uninstaller = Join-Path $installDir "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART"
        ) -Wait -PassThru
        $result.uninstall_exit_code = $uninstall.ExitCode
    }
    $result.ok = ($result.install_exit_code -eq 0 -and $result.app_launch.ok -and ($null -eq $result.uninstall_exit_code -or $result.uninstall_exit_code -eq 0))
}
finally {
    if (Test-Path -LiteralPath $installDir) {
        try {
            Remove-Item -LiteralPath $installDir -Recurse -Force
        }
        catch {
            $result.cleanup_error = $_.Exception.Message
        }
    }
}

$result | ConvertTo-Json -Depth 6
if (-not $result.ok) {
    exit 1
}
