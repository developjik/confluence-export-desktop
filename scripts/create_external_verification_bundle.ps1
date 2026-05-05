param(
    [string]$OutputDir,
    [string]$BundleName,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $repo "docs\verification\external_bundle"
}
if (-not $BundleName) {
    $BundleName = "confluence-export-desktop-external-verification-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

function Copy-RequiredItem {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required bundle source is missing: $Source"
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Get-RelativePath {
    param(
        [string]$RootPath,
        [string]$Path
    )
    $rootFull = (Resolve-Path -LiteralPath $RootPath).Path.TrimEnd("\")
    $pathFull = (Resolve-Path -LiteralPath $Path).Path
    return $pathFull.Substring($rootFull.Length).TrimStart("\")
}

function Get-BundleFiles {
    param([string]$RootPath)
    $files = Get-ChildItem -LiteralPath $RootPath -File -Recurse | Sort-Object FullName
    foreach ($file in $files) {
        $relative = Get-RelativePath -RootPath $RootPath -Path $file.FullName
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
        [pscustomobject]@{
            path = $relative
            bytes = $file.Length
            sha256 = $hash
        }
    }
}

$outputRoot = New-Item -ItemType Directory -Force -Path $OutputDir
$bundleDir = Join-Path $outputRoot.FullName $BundleName
if (Test-Path -LiteralPath $bundleDir) {
    $resolvedBundle = (Resolve-Path -LiteralPath $bundleDir).Path
    $resolvedOutput = (Resolve-Path -LiteralPath $outputRoot.FullName).Path
    if (-not $resolvedBundle.StartsWith($resolvedOutput)) {
        throw "Refusing to remove path outside output directory: $resolvedBundle"
    }
    Remove-Item -LiteralPath $resolvedBundle -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

$items = @(
    @{ source = "dist\confluence-export-desktop"; destination = "dist\confluence-export-desktop" },
    @{ source = "scripts\create_external_verification_bundle.ps1"; destination = "scripts\create_external_verification_bundle.ps1" },
    @{ source = "scripts\import_external_evidence.ps1"; destination = "scripts\import_external_evidence.ps1" },
    @{ source = "scripts\verify_external_gates.ps1"; destination = "scripts\verify_external_gates.ps1" },
    @{ source = "scripts\live_confluence_smoke.py"; destination = "scripts\live_confluence_smoke.py" },
    @{ source = "scripts\_path.py"; destination = "scripts\_path.py" },
    @{ source = "docs\verification\manual_verification_checklist.md"; destination = "docs\verification\manual_verification_checklist.md" },
    @{ source = "docs\verification\uat_observation_template.md"; destination = "docs\verification\uat_observation_template.md" },
    @{ source = "docs\verification\verification_report.md"; destination = "docs\verification\verification_report.md" },
    @{ source = "docs\verification\verification_report.json"; destination = "docs\verification\verification_report.json" },
    @{ source = "docs\verification\coverage_report.md"; destination = "docs\verification\coverage_report.md" },
    @{ source = "docs\verification\requirement_audit.md"; destination = "docs\verification\requirement_audit.md" },
    @{ source = "docs\verification\contract_audit.md"; destination = "docs\verification\contract_audit.md" },
    @{ source = "docs\verification\external_evidence_audit.md"; destination = "docs\verification\external_evidence_audit.md" },
    @{ source = "docs\verification\completion_audit.md"; destination = "docs\verification\completion_audit.md" }
)

$optionalCliDist = Join-Path $repo "dist\confluence-export-cli"
if (Test-Path -LiteralPath $optionalCliDist) {
    $items += @{ source = "dist\confluence-export-cli"; destination = "dist\confluence-export-cli" }
}

foreach ($item in $items) {
    Copy-RequiredItem -Source (Join-Path $repo $item.source) -Destination (Join-Path $bundleDir $item.destination)
}

$readme = @'
# Confluence Export Desktop External Verification Bundle

This bundle contains the built GUI app and the verification materials needed for the external gates.

## Clean Windows VM Package Gate

Run this on a clean Windows VM without Python installed:

```powershell
.\scripts\verify_external_gates.ps1 -Mode Package -EvidenceDir .\evidence
```

The clean VM gate is satisfied only when `external_gates.json` reports `python_install_detected: false` and the GUI package checks pass.

## Live Confluence Gate

Set the following environment variables before live verification:

```powershell
$env:CONFLUENCE_EXPORT_BASE_URL = "https://company.atlassian.net"
$env:CONFLUENCE_EXPORT_EMAIL = "user@example.com"
$env:CONFLUENCE_EXPORT_API_TOKEN = "<token>"
$env:CONFLUENCE_EXPORT_PAGE_URL = "https://company.atlassian.net/wiki/spaces/SPACE/pages/123456"
```

Then run one of:

```powershell
.\scripts\verify_external_gates.ps1 -Mode LiveConfluence -EvidenceDir .\evidence
python .\scripts\live_confluence_smoke.py
```

The live test page must have at least two child pages.

## UAT

Use `docs\verification\uat_observation_template.md` and save the completed record under `evidence` after the session.

## Importing Evidence Back Into The Repo

After the external run, copy the `evidence` folder or returned bundle zip back to the repo machine and run:

```powershell
.\scripts\import_external_evidence.ps1 -EvidencePath <path-to-evidence-folder-or-zip> -RunVerification
```

## Local References

- `docs\verification\manual_verification_checklist.md`
- `docs\verification\verification_report.md`
- `docs\verification\coverage_report.md`
- `docs\verification\completion_audit.md`
'@
Set-Content -Path (Join-Path $bundleDir "README_EXTERNAL_VERIFICATION.md") -Value $readme -Encoding UTF8

$files = @(Get-BundleFiles -RootPath $bundleDir)
$manifest = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    bundle_name = $BundleName
    file_count = $files.Count
    files = $files
}
$manifestPath = Join-Path $bundleDir "bundle_manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding UTF8

$zipPath = $null
if (-not $NoZip) {
    $zipPath = Join-Path $outputRoot.FullName ($BundleName + ".zip")
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $zipPath -Force
}

$result = [ordered]@{
    ok = $true
    bundle_dir = $bundleDir
    zip_path = $zipPath
    manifest_path = $manifestPath
    file_count = $files.Count
    gui_exe = (Join-Path $bundleDir "dist\confluence-export-desktop\confluence-export-desktop.exe")
}
$result | ConvertTo-Json -Depth 4
