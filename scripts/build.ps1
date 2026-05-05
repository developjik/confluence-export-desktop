param(
    [switch]$IncludeCli
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = $env:PYTHON_EXE
if (-not $python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        $python = $command.Source
    }
}
if (-not $python) {
    $localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $localPython) {
        $python = $localPython
    }
}
if (-not $python) {
    throw "Python not found. Set PYTHON_EXE to a Python 3.11+ executable."
}

& $python -m PyInstaller --noconfirm packaging\confluence-export-desktop.spec
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
if ($IncludeCli) {
    & $python -m PyInstaller --noconfirm packaging\confluence-export-cli.spec
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    $cliDist = Join-Path $repo "dist\confluence-export-cli"
    if (Test-Path -LiteralPath $cliDist) {
        $resolvedCliDist = (Resolve-Path -LiteralPath $cliDist).Path
        $resolvedDist = (Resolve-Path -LiteralPath (Join-Path $repo "dist")).Path
        if (-not $resolvedCliDist.StartsWith($resolvedDist)) {
            throw "Refusing to remove path outside dist: $resolvedCliDist"
        }
        Remove-Item -LiteralPath $cliDist -Recurse -Force
    }
}
