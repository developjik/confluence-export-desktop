param(
    [string]$Version = "0.1.0",
    [switch]$SkipAppBuild,
    [switch]$InstallInnoSetup
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Find-Iscc {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $candidates = @(
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$iscc = Find-Iscc
if (-not $iscc -and $InstallInnoSetup) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Inno Setup compiler not found and winget is unavailable. Install Inno Setup 6, then rerun this script."
    }
    & $winget.Source install --id JRSoftware.InnoSetup --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $iscc = Find-Iscc
}

if (-not $iscc) {
    throw "Inno Setup compiler not found. Install it with: winget install --id JRSoftware.InnoSetup --exact"
}

$appDir = Join-Path $repo "dist\confluence-export-desktop"
$appExe = Join-Path $appDir "confluence-export-desktop.exe"
if (-not (Test-Path -LiteralPath $appExe)) {
    throw "Built app missing: $appExe"
}

$env:CED_APP_VERSION = $Version
& $iscc (Join-Path $repo "packaging\confluence-export-desktop.iss")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$setup = Join-Path $repo "dist\ConfluenceExportDesktopSetup-$Version.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    throw "Installer was not created: $setup"
}

Get-FileHash -LiteralPath $setup -Algorithm SHA256 | Format-List Algorithm,Hash,Path
