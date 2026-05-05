param(
    [Parameter(Mandatory = $true)]
    [string]$EvidencePath,

    [string]$DestinationDir,
    [switch]$RunVerification
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
if (-not $DestinationDir) {
    $DestinationDir = Join-Path $repo "docs\verification\external_evidence"
}
if (-not [System.IO.Path]::IsPathRooted($DestinationDir)) {
    $DestinationDir = Join-Path (Get-Location).Path $DestinationDir
}
$DestinationDir = [System.IO.Path]::GetFullPath($DestinationDir)
New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null

function ConvertTo-SafeName {
    param([string]$Value)
    $safe = $Value -replace '[<>:"/\\|?*]', '_'
    if (-not $safe) {
        return "evidence"
    }
    return $safe
}

function Get-UniquePath {
    param([string]$Parent, [string]$Name)
    $baseName = ConvertTo-SafeName $Name
    $candidate = Join-Path $Parent $baseName
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }
    $suffix = 1
    while ($true) {
        $candidate = Join-Path $Parent "$baseName-$suffix"
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
        $suffix += 1
    }
}

function Test-EvidenceDirectory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }
    if (Test-Path -LiteralPath (Join-Path $Path "external_gates.json")) {
        return $true
    }
    if (Test-Path -LiteralPath (Join-Path $Path "live_confluence_smoke.json")) {
        return $true
    }
    $uatFiles = Get-ChildItem -LiteralPath $Path -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)uat' -and $_.Extension -in @(".md", ".txt", ".json") }
    return [bool]$uatFiles
}

function Find-EvidenceDirectories {
    param([string]$RootPath)
    $directories = @()
    if (Test-EvidenceDirectory -Path $RootPath) {
        $directories += (Resolve-Path -LiteralPath $RootPath).Path
    }
    $children = Get-ChildItem -LiteralPath $RootPath -Directory -Recurse -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        if (Test-EvidenceDirectory -Path $child.FullName) {
            $directories += $child.FullName
        }
    }
    return $directories | Sort-Object -Unique
}

function Copy-EvidenceDirectory {
    param([string]$SourceDir, [string]$DestinationRoot)
    $source = Resolve-Path -LiteralPath $SourceDir
    $destination = Get-UniquePath -Parent $DestinationRoot -Name (Split-Path -Leaf $source.Path)
    Copy-Item -LiteralPath $source.Path -Destination $destination -Recurse -Force
    return [pscustomobject]@{
        source = $source.Path
        destination = $destination
        kind = "directory"
    }
}

function Copy-EvidenceFile {
    param([string]$SourceFile, [string]$DestinationRoot)
    $source = Resolve-Path -LiteralPath $SourceFile
    $folder = Get-UniquePath -Parent $DestinationRoot -Name ("imported-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    Copy-Item -LiteralPath $source.Path -Destination (Join-Path $folder (Split-Path -Leaf $source.Path)) -Force
    return [pscustomobject]@{
        source = $source.Path
        destination = $folder
        kind = "file"
    }
}

$sourcePath = Resolve-Path -LiteralPath $EvidencePath
$temporaryRoot = $null
$importRoot = $sourcePath.Path
$imported = @()

try {
    if (Test-Path -LiteralPath $sourcePath.Path -PathType Leaf) {
        if ([System.IO.Path]::GetExtension($sourcePath.Path).Equals(".zip", [System.StringComparison]::OrdinalIgnoreCase)) {
            $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("confluence-sync-evidence-import-" + [guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
            Expand-Archive -LiteralPath $sourcePath.Path -DestinationPath $temporaryRoot -Force
            $importRoot = $temporaryRoot
        }
        else {
            $imported += Copy-EvidenceFile -SourceFile $sourcePath.Path -DestinationRoot $DestinationDir
        }
    }

    if (Test-Path -LiteralPath $importRoot -PathType Container) {
        $candidates = @(Find-EvidenceDirectories -RootPath $importRoot)
        if ($candidates.Count -eq 0) {
            throw "No supported evidence directories were found. Expected external_gates.json, live_confluence_smoke.json, or UAT files."
        }
        foreach ($candidate in $candidates) {
            $imported += Copy-EvidenceDirectory -SourceDir $candidate -DestinationRoot $DestinationDir
        }
    }

    $verification = $null
    if ($RunVerification) {
        $verify = Join-Path $repo "scripts\verify_release.py"
        $proc = Start-Process -FilePath "python" -ArgumentList @($verify) -WorkingDirectory $repo -NoNewWindow -PassThru -Wait
        $verification = [pscustomobject]@{ exit_code = $proc.ExitCode }
    }

    [ordered]@{
        ok = $true
        destination_dir = $DestinationDir
        imported_count = $imported.Count
        imported = $imported
        verification = $verification
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
