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

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "== $Name" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK: $Name" -ForegroundColor Green
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

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
