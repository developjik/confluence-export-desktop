param(
    [ValidateSet("Package", "LiveConfluence", "All")]
    [string]$Mode = "Package",

    [string]$BaseUrl = $env:CONFLUENCE_SYNC_BASE_URL,
    [string]$Email = $env:CONFLUENCE_SYNC_EMAIL,
    [string]$ApiToken = $env:CONFLUENCE_SYNC_API_TOKEN,
    [string]$PageUrl = $env:CONFLUENCE_SYNC_PAGE_URL,

    [string]$EvidenceDir,
    [switch]$NoGui,
    [switch]$SkipRelocation,
    [switch]$DevelopmentSmoke
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
if (-not $EvidenceDir) {
    $EvidenceDir = Join-Path $repo "docs\verification\external_evidence"
}
if (-not [System.IO.Path]::IsPathRooted($EvidenceDir)) {
    $EvidenceDir = Join-Path (Get-Location).Path $EvidenceDir
}
$EvidenceDir = [System.IO.Path]::GetFullPath($EvidenceDir)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $EvidenceDir $timestamp
$runDir = (New-Item -ItemType Directory -Force -Path $runDir).FullName

function ConvertTo-SafeFileName {
    param([string]$Value)
    return ($Value -replace '[<>:"/\\|?*]', '_')
}

function Get-System32Path {
    $systemRoot = $env:SystemRoot
    if (-not $systemRoot) {
        $systemRoot = $env:WINDIR
    }
    if (-not $systemRoot) {
        $systemRoot = "C:\Windows"
    }
    return Join-Path $systemRoot "System32"
}

function Invoke-WithEnv {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [hashtable]$ExtraEnv = @{},
        [string]$InputText = $null,
        [string]$Redact = $null,
        [string]$EvidenceLabel = "",
        [int]$TimeoutSeconds = 120
    )

    if (-not (Test-Path -LiteralPath $Exe)) {
        return [pscustomobject]@{
            ok = $false
            exe = $Exe
            args = $Arguments
            exit_code = 127
            stdout = ""
            stderr = "Executable not found"
        }
    }

    $oldEnv = @{}
    foreach ($key in $ExtraEnv.Keys) {
        $oldEnv[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$ExtraEnv[$key], "Process")
    }

    try {
        $baseName = (Split-Path -Leaf $Exe) + "-" + ($Arguments -join "-")
        if ($EvidenceLabel) {
            $baseName = $EvidenceLabel + "-" + $baseName
        }
        $safeName = ConvertTo-SafeFileName $baseName
        if ($safeName.Length -gt 120) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($safeName)
            $sha = [System.Security.Cryptography.SHA256]::Create()
            $hash = (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 16)
            $safeName = $safeName.Substring(0, 96) + "-" + $hash
        }
        $outputFile = Join-Path $runDir ("stdout-" + $safeName + ".txt")
        $errorFile = Join-Path $runDir ("stderr-" + $safeName + ".txt")
        $job = Start-Job -ScriptBlock {
            param($ExePath, $ArgsList, $InputValue, $OutPath, $ErrPath, $EnvMap)
            foreach ($key in $EnvMap.Keys) {
                [Environment]::SetEnvironmentVariable($key, [string]$EnvMap[$key], "Process")
            }
            $utf8 = New-Object System.Text.UTF8Encoding $false
            [Console]::OutputEncoding = $utf8
            $OutputEncoding = $utf8
            & "$env:SystemRoot\System32\chcp.com" 65001 > $null
            if ($null -eq $InputValue) {
                & $ExePath @ArgsList 1> $OutPath 2> $ErrPath
            }
            else {
                $InputValue | & $ExePath @ArgsList 1> $OutPath 2> $ErrPath
            }
            return $LASTEXITCODE
        } -ArgumentList $Exe, $Arguments, $InputText, $outputFile, $errorFile, $ExtraEnv

        if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
            Stop-Job $job | Out-Null
            Remove-Job $job | Out-Null
            return [pscustomobject]@{
                ok = $false
                exe = $Exe
                args = $Arguments
                exit_code = 124
                stdout = ""
                stderr = "Timed out after $TimeoutSeconds seconds"
            }
        }

        $exitCode = Receive-Job $job
        Remove-Job $job | Out-Null
        $stdout = ""
        if (Test-Path -LiteralPath $outputFile) {
            $stdout = [string](Get-Content -Raw -Path $outputFile)
        }
        $stderr = ""
        if (Test-Path -LiteralPath $errorFile) {
            $stderr = [string](Get-Content -Raw -Path $errorFile)
        }
        if ($null -eq $stdout) {
            $stdout = ""
        }
        if ($null -eq $stderr) {
            $stderr = ""
        }
        if ($Redact) {
            $stdout = $stdout.Replace($Redact, "****")
            $stderr = $stderr.Replace($Redact, "****")
        }
        Set-Content -Path $outputFile -Value $stdout -Encoding UTF8
        Set-Content -Path $errorFile -Value $stderr -Encoding UTF8
        return [pscustomobject]@{
            ok = ([int]$exitCode -eq 0)
            exe = $Exe
            args = $Arguments
            exit_code = [int]$exitCode
            stdout_file = $outputFile
            stderr_file = $errorFile
            stdout_tail = (Get-TextTail -Value $stdout)
            stderr_tail = (Get-TextTail -Value $stderr)
        }
    }
    finally {
        foreach ($key in $ExtraEnv.Keys) {
            [Environment]::SetEnvironmentVariable($key, $oldEnv[$key], "Process")
        }
    }
}

function Get-TextTail {
    param([object]$Value, [int]$Length = 3000)
    if ($null -eq $Value) {
        return ""
    }
    $text = [string]$Value
    return $text.Substring([Math]::Max(0, $text.Length - $Length))
}

function Start-GuiSmoke {
    param(
        [string]$GuiExe,
        [hashtable]$ExtraEnv = @{},
        [int]$Seconds = 5
    )

    if ($NoGui) {
        return [pscustomobject]@{ ok = $true; skipped = $true; reason = "NoGui switch was set" }
    }
    if (-not (Test-Path -LiteralPath $GuiExe)) {
        return [pscustomobject]@{ ok = $false; path = $GuiExe; reason = "GUI executable not found" }
    }

    $oldEnv = @{}
    foreach ($key in $ExtraEnv.Keys) {
        $oldEnv[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$ExtraEnv[$key], "Process")
    }

    try {
        $proc = Start-Process -FilePath $GuiExe -WorkingDirectory (Split-Path -Parent $GuiExe) -PassThru
        Start-Sleep -Seconds $Seconds
        $running = -not $proc.HasExited
        if ($running) {
            Stop-Process -Id $proc.Id -Force
        }
        return [pscustomobject]@{ ok = $running; path = $GuiExe; running_after_seconds = $Seconds; pid = $proc.Id }
    }
    finally {
        foreach ($key in $ExtraEnv.Keys) {
            [Environment]::SetEnvironmentVariable($key, $oldEnv[$key], "Process")
        }
    }
}

function Get-TreeHash {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return "missing"
    }

    $files = Get-ChildItem -LiteralPath $Path -File -Recurse | Sort-Object FullName
    if (-not $files) {
        return "empty"
    }

    $hashInput = New-Object System.Text.StringBuilder
    foreach ($file in $files) {
        $relative = $file.FullName.Substring((Resolve-Path -LiteralPath $Path).Path.Length).TrimStart("\")
        $fileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash
        [void]$hashInput.AppendLine("$relative $fileHash")
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($hashInput.ToString())
    $sha = [System.Security.Cryptography.SHA256]::Create()
    return (($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Get-PreviewItemCount {
    param([object]$PreviewResult)
    try {
        if ($PreviewResult -and $PreviewResult.stdout_file -and (Test-Path -LiteralPath $PreviewResult.stdout_file)) {
            $previewJson = Get-Content -Raw -Encoding UTF8 -LiteralPath $PreviewResult.stdout_file | ConvertFrom-Json
            return @($previewJson.items).Count
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-ExportSummary {
    param([string]$Workspace)
    if (-not (Test-Path -LiteralPath $Workspace)) {
        return [pscustomobject]@{ exists = $false; file_count = 0; markdown_count = 0; lockfile_exists = $false; paths = @() }
    }
    $files = @(Get-ChildItem -LiteralPath $Workspace -File -Recurse -ErrorAction SilentlyContinue)
    $paths = @()
    foreach ($file in $files | Select-Object -First 50) {
        $paths += $file.FullName.Substring((Resolve-Path -LiteralPath $Workspace).Path.Length).TrimStart("\")
    }
    $markdown = @($files | Where-Object { $_.Extension -ieq ".md" })
    return [pscustomobject]@{
        exists = $true
        file_count = $files.Count
        markdown_count = $markdown.Count
        lockfile_exists = (Test-Path -LiteralPath (Join-Path $Workspace "confluence-lock.json"))
        paths = $paths
    }
}

function Get-PythonInstallSignal {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    $registryPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $registryEntries = @()
    foreach ($registryPath in $registryPaths) {
        $items = Get-ItemProperty -Path $registryPath -ErrorAction SilentlyContinue |
            Where-Object {
                $_.DisplayName -and ($_.DisplayName -match "Python|PyPy|Anaconda|Miniconda")
            }
        foreach ($item in $items) {
            $registryEntries += [pscustomobject]@{
                display_name = $item.DisplayName
                display_version = $item.DisplayVersion
                install_location = $item.InstallLocation
            }
        }
    }
    $pythonOnPath = [bool]$pythonCommand
    $pyLauncherOnPath = [bool]$pyCommand
    $registryEntryCount = @($registryEntries).Count
    $pythonInstallDetected = $pythonOnPath -or $pyLauncherOnPath -or ($registryEntryCount -gt 0)
    return [pscustomobject]@{
        python_on_path = $pythonOnPath
        python_path = if ($pythonCommand) { $pythonCommand.Source } else { $null }
        py_launcher_on_path = $pyLauncherOnPath
        py_launcher_path = if ($pyCommand) { $pyCommand.Source } else { $null }
        python_registry_entry_count = $registryEntryCount
        python_registry_entries = $registryEntries
        python_install_detected = $pythonInstallDetected
        pass_requires_python_on_path_false = (-not $pythonOnPath)
        pass_requires_no_python_install_signal = (-not $pythonInstallDetected)
    }
}

function Test-PackageGate {
    param([string]$RootPath, [string]$Label)

    $gui = Join-Path $RootPath "dist\confluence-sync\confluence-sync.exe"
    $cleanEnv = @{ PATH = (Get-System32Path) }
    $pythonSignal = Get-PythonInstallSignal
    $guiSmoke = Start-GuiSmoke -GuiExe $gui -ExtraEnv $cleanEnv -Seconds 5

    $guiSkipped = [bool]$guiSmoke.skipped
    $pythonRequirementOk = (-not $pythonSignal.python_install_detected) -or $DevelopmentSmoke
    $guiRequirementOk = ($guiSmoke.ok -and (-not $guiSkipped)) -or ($DevelopmentSmoke -and $guiSmoke.ok)
    $smokeOk = ((Test-Path -LiteralPath $gui) -and $guiSmoke.ok)
    $gateOk = ((Test-Path -LiteralPath $gui) -and $guiRequirementOk -and $pythonRequirementOk)

    return [pscustomobject]@{
        label = $Label
        development_smoke = [bool]$DevelopmentSmoke
        clean_vm_signal = $pythonSignal
        gui_exists = (Test-Path -LiteralPath $gui)
        gui_launch = $guiSmoke
        smoke_ok = $smokeOk
        ok = $gateOk
    }
}

function Copy-RelocatedDist {
    $destinationRoot = Join-Path $runDir "relocated"
    $destinationDist = Join-Path $destinationRoot "dist"
    if (Test-Path -LiteralPath $destinationRoot) {
        $resolvedDestination = (Resolve-Path -LiteralPath $destinationRoot).Path
        $resolvedRunDir = (Resolve-Path -LiteralPath $runDir).Path
        if (-not $resolvedDestination.StartsWith($resolvedRunDir)) {
            throw "Refusing to remove path outside evidence directory: $resolvedDestination"
        }
        Remove-Item -LiteralPath $destinationRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $destinationDist | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo "dist\confluence-sync") -Destination $destinationDist -Recurse
    $cliDist = Join-Path $repo "dist\confluence-sync-cli"
    if (Test-Path -LiteralPath $cliDist) {
        Copy-Item -LiteralPath $cliDist -Destination $destinationDist -Recurse
    }
    return $destinationRoot
}

function Test-LiveConfluenceGate {
    $missing = @()
    if (-not $BaseUrl) { $missing += "CONFLUENCE_SYNC_BASE_URL" }
    if (-not $Email) { $missing += "CONFLUENCE_SYNC_EMAIL" }
    if (-not $ApiToken) { $missing += "CONFLUENCE_SYNC_API_TOKEN" }
    if (-not $PageUrl) { $missing += "CONFLUENCE_SYNC_PAGE_URL" }
    if ($missing.Count -gt 0) {
        return [pscustomobject]@{
            ok = $false
            missing_env = $missing
            note = "Set the missing environment variables and rerun with -Mode LiveConfluence."
        }
    }

    $cli = Join-Path $repo "dist\confluence-sync-cli\confluence-sync-cli.exe"
    $systemDrive = $env:SystemDrive
    if (-not $systemDrive) {
        $systemDrive = "C:"
    }
    $shortRoot = Join-Path ($systemDrive + "\") ("cst-" + $timestamp)
    try {
        New-Item -ItemType Directory -Force -Path $shortRoot | Out-Null
    }
    catch {
        $shortRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("cst-" + $timestamp)
    }
    $appData = Join-Path $shortRoot "a"
    $workspace = Join-Path $shortRoot "w"
    $workspaceForCli = $workspace
    if ($workspaceForCli -match "^[A-Za-z]:\\") {
        $workspaceForCli = "\\?\" + $workspaceForCli
    }
    New-Item -ItemType Directory -Force -Path $appData, $workspace | Out-Null
    $envBlock = @{
        APPDATA = $appData
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
    }
    $jobId = "live-smoke-$timestamp"

    $login = Invoke-WithEnv -Exe $cli -Arguments @("login", "--base-url", $BaseUrl, "--email", $Email, "--token-stdin", "--test") -ExtraEnv $envBlock -InputText $ApiToken -Redact $ApiToken -EvidenceLabel "live-login" -TimeoutSeconds 120
    $addJob = Invoke-WithEnv -Exe $cli -Arguments @("add-job", "--job-id", $jobId, "--name", "Live Smoke", "--url", $PageUrl, "--target-dir", $workspaceForCli, "--include-children") -ExtraEnv $envBlock -Redact $ApiToken -EvidenceLabel "live-add-job" -TimeoutSeconds 60
    $preview = Invoke-WithEnv -Exe $cli -Arguments @("preview", "--job", $jobId) -ExtraEnv $envBlock -Redact $ApiToken -EvidenceLabel "live-preview" -TimeoutSeconds 120
    $beforeDryRunHash = Get-TreeHash -Path $workspace
    $dryRun = Invoke-WithEnv -Exe $cli -Arguments @("dry-run", "--job", $jobId) -ExtraEnv $envBlock -Redact $ApiToken -EvidenceLabel "live-dry-run" -TimeoutSeconds 120
    $afterDryRunHash = Get-TreeHash -Path $workspace
    $run = Invoke-WithEnv -Exe $cli -Arguments @("run", "--job", $jobId) -ExtraEnv $envBlock -Redact $ApiToken -EvidenceLabel "live-run" -TimeoutSeconds 180
    $logout = Invoke-WithEnv -Exe $cli -Arguments @("logout") -ExtraEnv $envBlock -Redact $ApiToken -EvidenceLabel "live-logout" -TimeoutSeconds 60

    $previewItems = Get-PreviewItemCount -PreviewResult $preview
    $exportSummary = Get-ExportSummary -Workspace $workspace
    $tokenLeaks = @()
    foreach ($rootPath in @($appData, $workspace)) {
        if (Test-Path -LiteralPath $rootPath) {
            $matches = Get-ChildItem -LiteralPath $rootPath -File -Recurse | Select-String -SimpleMatch $ApiToken -ErrorAction SilentlyContinue
            foreach ($match in $matches) {
                $tokenLeaks += $match.Path
            }
        }
    }

    return [pscustomobject]@{
        ok = ($login.ok -and $addJob.ok -and $preview.ok -and $dryRun.ok -and $run.ok -and $logout.ok -and ($beforeDryRunHash -eq $afterDryRunHash) -and ($exportSummary.file_count -gt 0) -and ($tokenLeaks.Count -eq 0))
        job_id = $jobId
        workspace = $workspace
        appdata = $appData
        login = $login
        add_job = $addJob
        preview = $preview
        dry_run = $dryRun
        run = $run
        logout = $logout
        dry_run_hash_before = $beforeDryRunHash
        dry_run_hash_after = $afterDryRunHash
        preview_items = $previewItems
        export = $exportSummary
        token_leak_files = $tokenLeaks
    }
}

$result = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    mode = $Mode
    evidence_dir = $runDir
    package = $null
    package_relocated = $null
    live_confluence = $null
}

if ($Mode -eq "Package" -or $Mode -eq "All") {
    $result.package = Test-PackageGate -RootPath $repo -Label "repository-dist"
    if (-not $SkipRelocation) {
        $relocatedRoot = Copy-RelocatedDist
        $result.package_relocated = Test-PackageGate -RootPath $relocatedRoot -Label "relocated-dist"
    }
}

if ($Mode -eq "LiveConfluence" -or $Mode -eq "All") {
    $result.live_confluence = Test-LiveConfluenceGate
}

$jsonPath = Join-Path $runDir "external_gates.json"
$result | ConvertTo-Json -Depth 12 | Set-Content -Path $jsonPath -Encoding UTF8
Get-Content -Raw -Path $jsonPath

$packageOk = ($null -eq $result.package -or $result.package.ok) -and ($null -eq $result.package_relocated -or $result.package_relocated.ok)
$liveOk = ($null -eq $result.live_confluence -or $result.live_confluence.ok)
if ($packageOk -and $liveOk) {
    exit 0
}
exit 1
