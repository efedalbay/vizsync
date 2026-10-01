<#
.SYNOPSIS
    Checks that have to run on Efe's Windows computer.

.DESCRIPTION
    Run from PowerShell, from anywhere: .\scripts\check-local.ps1
    It pulls the latest code, then runs the steps in check-steps.ps1. The steps live in a
    second file so that the pull has already brought them up to date when they start.

.PARAMETER SkipPull
    Do not run "git pull". CI uses this, because it already has the right commit.

.PARAMETER NoModel
    Skip the steps that need the real speech model. CI uses this.

.PARAMETER Speed
    Also measure recognition speed on a clip of about 13 minutes (takes a few minutes).
#>
param(
    [switch]$SkipPull,
    [switch]$NoModel,
    [switch]$Speed
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $SkipPull) {
    Write-Host ""
    Write-Host "== git pull" -ForegroundColor Cyan
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: git pull (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK: git pull" -ForegroundColor Green
}

& "$PSScriptRoot\check-steps.ps1" -NoModel:$NoModel -Speed:$Speed
exit $LASTEXITCODE
