<#
.SYNOPSIS
    The checks that have to run on Efe's Windows computer. Started by check-local.ps1.

.DESCRIPTION
    Each milestone adds its own checks in the "Milestone checks" section at the bottom.
    The script stops at the first step that fails and says which one.

.PARAMETER NoModel
    Skip the steps that need the real speech model. CI uses this.

.PARAMETER Speed
    Also measure recognition speed on a clip of about 13 minutes (takes a few minutes).
#>
param(
    [switch]$NoModel,
    [switch]$Speed
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-ExpectingExitCode {
    param(
        [string]$Name,
        [int]$Expected,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "== $Name" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Command
    if ($LASTEXITCODE -ne $Expected) {
        Write-Host "FAILED: $Name (exit code $LASTEXITCODE, expected $Expected)" -ForegroundColor Red
        exit 1
    }
    $global:LASTEXITCODE = 0
    Write-Host "OK: $Name" -ForegroundColor Green
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Invoke-ExpectingExitCode $Name 0 $Command
}

Invoke-Step "Current commit" { git log -1 --oneline }
Invoke-Step "uv sync" { uv sync }
Invoke-Step "Fast tests" { uv run pytest -m "not slow" }
Invoke-Step "vizsync --version" { uv run vizsync --version }

# --- Milestone checks ---------------------------------------------------------
# Add the checks that need this computer (real-model tests, hand checks) below,
# one Invoke-Step per check, in the milestone that introduces them.
# M0: none.

# M1: the example script is valid, a broken one fails with exit code 1.
Invoke-Step "check: example script" { uv run vizsync check examples/northwind-script.md }
Invoke-Step "check: example script, inline mode" {
    uv run vizsync check examples/northwind-script.md --text inline
}
Invoke-ExpectingExitCode "check: broken script exits with 1" 1 {
    uv run vizsync check tests/unit/fixtures/several_errors.md
}

# M2: the aligner benchmark on this computer. It must finish in under 10 seconds.
Invoke-Step "aligner benchmark" {
    uv run pytest tests/unit/test_aligner_benchmark.py --durations=3
}

# M3: the real speech model on the fixture clip. The first run downloads the model.
if ($NoModel) {
    Write-Host ""
    Write-Host "Skipped the real-model steps (-NoModel)." -ForegroundColor Yellow
}
elseif (-not (Test-Path "tests/fixtures/northwind.wav")) {
    Write-Host ""
    Write-Host "Skipped the real-model steps: tests/fixtures/northwind.wav does not exist yet." -ForegroundColor Yellow
}
else {
    Invoke-Step "slow tests (real speech model)" { uv run pytest -m slow -rs }
    Invoke-Step "align: fixture clip" {
        uv run vizsync align tests/fixtures/northwind.wav --script examples/northwind-script.md --out out/fixture
    }
}

# M3: recognition speed on about 13 minutes of audio, for the README. Only with -Speed.
if ($Speed -and -not $NoModel -and (Test-Path "tests/fixtures/northwind.wav")) {
    Invoke-Step "speed: build a 13-minute clip" {
        uv run python scripts/make-long-clip.py tests/fixtures/northwind.wav out/speed/long.wav --minutes 13
    }
    Invoke-Step "speed: this computer" {
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        $ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
        Write-Host "CPU: $($cpu.Name), $($cpu.NumberOfCores) cores, $($cpu.NumberOfLogicalProcessors) threads"
        Write-Host "RAM: $ram GB"
    }
    Write-Host ""
    Write-Host "== speed: align 13 minutes (small.en)" -ForegroundColor Cyan
    uv run vizsync align out/speed/long.wav --script examples/northwind-script.md --out out/speed --formats json
    # Exit code 2 would only mean a paragraph was not found; speed is what counts here.
    if ($LASTEXITCODE -gt 2) {
        Write-Host "FAILED: speed: align 13 minutes (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    $global:LASTEXITCODE = 0
    Write-Host "OK: speed: align 13 minutes" -ForegroundColor Green
}

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
exit 0
