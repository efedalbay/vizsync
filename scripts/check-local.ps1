<#
.SYNOPSIS
    Checks that have to run on Efe's Windows computer.

.DESCRIPTION
    Run from PowerShell, from anywhere: .\scripts\check-local.ps1
    Each milestone adds its own checks in the "Milestone checks" section at the bottom.
    The script stops at the first step that fails and says which one.

.PARAMETER SkipPull
    Do not run "git pull". CI uses this, because it already has the right commit.
#>
param(
    [switch]$SkipPull
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

if (-not $SkipPull) {
    Invoke-Step "git pull" { git pull --ff-only }
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

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
exit 0
