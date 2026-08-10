[CmdletBinding()]
param(
    [switch]$ValidateOnly,
    [switch]$CompileAll
)

$ErrorActionPreference = "Stop"

$Repo = $PSScriptRoot
$MetaEditor = "C:\MT5\MetaEditor64.exe"
$LogDirectory = Join-Path $Repo ".compile-logs"
$EnvFile = Join-Path $Repo ".env"
$CanonicalDirectory = Join-Path $Repo "mq5"
$EaNames = @("Webhook1.mq5", "Webhook2.mq5", "BigMove.mq5", "TPSL.mq5", "Overtrade.mq5")

function Get-ExpertsDirectory {
    if ($env:MT5_EXPERTS_DIR) {
        return $env:MT5_EXPERTS_DIR
    }

    if (Test-Path $EnvFile) {
        $setting = Get-Content $EnvFile |
            Where-Object { $_ -match '^MT5_EXPERTS_DIR=' } |
            Select-Object -First 1
        if ($setting) {
            return ($setting -replace '^MT5_EXPERTS_DIR=', '').Trim().Trim('"').Trim("'")
        }
    }

    $terminalRoot = Join-Path $env:APPDATA "MetaQuotes\Terminal"
    $matches = @(
        Get-ChildItem $terminalRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "MQL5\Experts" } |
            Where-Object { Test-Path (Join-Path $_ "Webhook1.mq5") }
    )

    if ($matches.Count -eq 1) {
        return $matches[0]
    }

    throw "Could not determine the live MT5 Experts directory. Set MT5_EXPERTS_DIR in .env."
}

if (-not (Test-Path $MetaEditor -PathType Leaf)) {
    throw "MetaEditor was not found: $MetaEditor"
}
if (-not (Test-Path $CanonicalDirectory -PathType Container)) {
    throw "Canonical MQL5 directory was not found: $CanonicalDirectory"
}

$ExpertsDirectory = Get-ExpertsDirectory
if (-not (Test-Path $ExpertsDirectory -PathType Container)) {
    throw "MT5 Experts directory was not found: $ExpertsDirectory"
}

Write-Host "Repository:  $Repo"
Write-Host "MetaEditor:  $MetaEditor"
Write-Host "Live Experts: $ExpertsDirectory"

if ($ValidateOnly) {
    foreach ($ea in $EaNames) {
        $canonical = Join-Path $CanonicalDirectory $ea
        $live = Join-Path $ExpertsDirectory $ea
        if (-not (Test-Path $canonical -PathType Leaf)) {
            throw "Canonical EA was not found: $canonical"
        }
        if (-not (Test-Path $live -PathType Leaf)) {
            throw "Live EA was not found: $live"
        }
    }
    Write-Host "Validation passed. No pull, synchronization, or compilation was performed."
    exit 0
}

Set-Location $Repo

$Before = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the current Git revision."
}

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    throw "git pull --ff-only failed. Local changes were left untouched."
}

$After = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the updated Git revision."
}

if (($Before -eq $After) -and (-not $CompileAll)) {
    Write-Host "Already up to date; no EAs require compilation."
    exit 0
}

$ChangedMqFiles = @()
if ($Before -ne $After) {
    $ChangedMqFiles = @(
        git diff --name-only --diff-filter=ACMRT $Before $After -- "mq5/*.mq5" "mq5/*.mqh"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Could not determine which MQL5 files changed."
    }
}

if ((-not $CompileAll) -and ($ChangedMqFiles.Count -eq 0)) {
    Write-Host "The pull contained no MQL5 source changes; nothing to synchronize or compile."
    exit 0
}

Write-Host "Synchronizing canonical MQL5 sources to the live Experts directory..."
python (Join-Path $Repo "sync_mq5.py")
if ($LASTEXITCODE -ne 0) {
    throw "MQL5 synchronization failed; compilation was not started."
}

$IncludeChanged = @($ChangedMqFiles | Where-Object { $_ -match '\.mqh$' }).Count -gt 0
if ($CompileAll -or $IncludeChanged) {
    $FilesToCompile = @($EaNames | ForEach-Object { Join-Path $ExpertsDirectory $_ })
    if ($IncludeChanged) {
        Write-Host "A shared include changed; compiling all live EAs."
    }
}
else {
    $changedEaNames = @(
        $ChangedMqFiles |
            Where-Object { $_ -match '\.mq5$' } |
            ForEach-Object { Split-Path $_ -Leaf } |
            Where-Object { $EaNames -contains $_ } |
            Select-Object -Unique
    )
    $FilesToCompile = @($changedEaNames | ForEach-Object { Join-Path $ExpertsDirectory $_ })
}

if ($FilesToCompile.Count -eq 0) {
    Write-Host "Sources were synchronized, but no EA entry point requires compilation."
    exit 0
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$Failed = @()

foreach ($SourceFile in $FilesToCompile) {
    if (-not (Test-Path $SourceFile -PathType Leaf)) {
        $Failed += $SourceFile
        Write-Host "FAILED: live source was not found: $SourceFile" -ForegroundColor Red
        continue
    }

    $EaName = Split-Path $SourceFile -Leaf
    $LogFile = Join-Path $LogDirectory ($EaName + ".log")
    Remove-Item $LogFile -Force -ErrorAction SilentlyContinue

    Write-Host "Compiling $EaName..."
    $Process = Start-Process `
        -FilePath $MetaEditor `
        -ArgumentList @(
            "/compile:`"$SourceFile`"",
            "/log:`"$LogFile`""
        ) `
        -Wait `
        -PassThru

    $LogText = if (Test-Path $LogFile) {
        Get-Content $LogFile -Raw
    }
    else {
        ""
    }

    $BinaryFile = [IO.Path]::ChangeExtension($SourceFile, ".ex5")
    if (($LogText -notmatch '\b0 errors?\b') -or (-not (Test-Path $BinaryFile -PathType Leaf))) {
        $Failed += $EaName
        Write-Host "FAILED: $EaName" -ForegroundColor Red
        if ($LogText) {
            Write-Host $LogText
        }
        elseif ($Process.ExitCode -ne 0) {
            Write-Host "MetaEditor exited with code $($Process.ExitCode) and produced no compile log."
        }
        else {
            Write-Host "MetaEditor produced no compile log."
        }
    }
    else {
        Write-Host "OK: $EaName" -ForegroundColor Green
    }
}

if ($Failed.Count -gt 0) {
    Write-Host "Compilation failed for:" -ForegroundColor Red
    $Failed | ForEach-Object { Write-Host " - $_" }
    exit 1
}

Write-Host "All affected live EAs compiled successfully." -ForegroundColor Green
exit 0
