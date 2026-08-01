#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the full public test suite for the remote-ac-controller monorepo.

.DESCRIPTION
    Single entry point for verifying the repository locally.

    Scope, by design:
      * Firmware  : delegated to firmware/tools/dev.ps1 (the ONLY supported
                    entry point). This script never invokes pio.exe directly.
      * Cloud     : backend and frontend unit tests plus TypeScript checks.

    Hard exclusions:
      * Never touches production hosts, production credentials or the broker.
      * Never flashes, uploads to or opens a serial port on any device.
      * Never reads anything outside this repository.
      * Never uses a non-public firmware profile.

.PARAMETER SkipFirmware
    Skip the firmware portion (useful on a machine without PlatformIO Core).

.PARAMETER SkipCloud
    Skip the cloud portion (useful on a machine without Node.js 24+).

.EXAMPLE
    pwsh tools/test-all.ps1

.EXAMPLE
    pwsh tools/test-all.ps1 -SkipFirmware
#>
[CmdletBinding()]
param(
    [switch] $SkipFirmware,
    [switch] $SkipCloud
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- constants ---------------------------------------------------------------
$RepoRoot     = Split-Path -Parent $PSScriptRoot
$FirmwareDir  = Join-Path $RepoRoot 'firmware/agent-platformio'
$DevScript    = Join-Path $FirmwareDir 'tools/dev.ps1'
$CloudBackend = Join-Path $RepoRoot 'cloud/backend'
$CloudFront   = Join-Path $RepoRoot 'cloud/frontend'
$Profile      = 'public'   # public profile only. Never private / private-production / ir-lab.

$script:Results = [System.Collections.Generic.List[object]]::new()

# --- helpers -----------------------------------------------------------------
function Write-Section {
    param([Parameter(Mandatory)][string] $Title)
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkGray
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkGray
}

function Add-Result {
    param(
        [Parameter(Mandatory)][string] $Name,
        [Parameter(Mandatory)][string] $Status,
        [string] $Detail = ''
    )
    $script:Results.Add([pscustomobject]@{
        Step   = $Name
        Status = $Status
        Detail = $Detail
    })
}

function Invoke-Step {
    <#
        Runs a scriptblock, records PASS/FAIL, and never aborts the whole run
        so that the final summary always lists every step.
    #>
    param(
        [Parameter(Mandatory)][string]      $Name,
        [Parameter(Mandatory)][scriptblock] $Action
    )
    Write-Section $Name
    try {
        & $Action
        if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
        Add-Result -Name $Name -Status 'PASS'
        Write-Host "PASS  $Name" -ForegroundColor Green
    }
    catch {
        Add-Result -Name $Name -Status 'FAIL' -Detail $_.Exception.Message
        Write-Host "FAIL  $Name : $($_.Exception.Message)" -ForegroundColor Red
    }
    finally {
        $global:LASTEXITCODE = 0
    }
}

function Invoke-NodeStep {
    param(
        [Parameter(Mandatory)][string]   $Name,
        [Parameter(Mandatory)][string]   $WorkingDirectory,
        [Parameter(Mandatory)][string]   $Executable,
        [Parameter(Mandatory)][string[]] $Arguments
    )
    Invoke-Step -Name $Name -Action {
        Push-Location -LiteralPath $WorkingDirectory
        try {
            # PowerShell 5.1 + $ErrorActionPreference='Stop' converts native
            # stderr lines (e.g. Vite CJS deprecation warnings) into
            # terminating errors even when the process exits 0, which would
            # false-FAIL the step. Drop EAP for the native call, keep the real
            # exit code, then restore.
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
                $nativeCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $prevEap
            }
            if ($nativeCode -ne 0) { throw "exit code $nativeCode" }
        }
        finally { Pop-Location }
    }
}

# --- guards ------------------------------------------------------------------
if (Test-Path -LiteralPath (Join-Path $RepoRoot 'Private')) {
    throw 'GUARD_FAIL: a Private/ directory exists in the repository. It must never be present.'
}

Write-Host ''
Write-Host 'remote-ac-controller :: test-all' -ForegroundColor White
Write-Host "repository : $RepoRoot"
Write-Host "profile    : $Profile (public only)"
Write-Host "started    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- firmware ----------------------------------------------------------------
if ($SkipFirmware) {
    Add-Result -Name 'firmware' -Status 'SKIP' -Detail '-SkipFirmware'
    Write-Host 'firmware: skipped by request' -ForegroundColor Yellow
}
elseif (-not (Test-Path -LiteralPath $DevScript)) {
    Add-Result -Name 'firmware' -Status 'SKIP' -Detail 'firmware/tools/dev.ps1 not found'
    Write-Host 'firmware: dev.ps1 not found, skipped' -ForegroundColor Yellow
}
else {
    Invoke-Step -Name 'firmware :: dev.ps1 status' -Action {
        & $DevScript -Command status
        if ($LASTEXITCODE -ne 0) { throw "dev.ps1 status exit code $LASTEXITCODE" }
    }

    Invoke-Step -Name 'firmware :: dev.ps1 test' -Action {
        & $DevScript -Command test -Profile $Profile
        if ($LASTEXITCODE -ne 0) { throw "dev.ps1 test exit code $LASTEXITCODE" }
    }

    Invoke-Step -Name 'firmware :: dev.ps1 verify' -Action {
        & $DevScript -Command verify -Profile $Profile
        if ($LASTEXITCODE -ne 0) { throw "dev.ps1 verify exit code $LASTEXITCODE" }
    }
}

# --- cloud -------------------------------------------------------------------
if ($SkipCloud) {
    Add-Result -Name 'cloud' -Status 'SKIP' -Detail '-SkipCloud'
    Write-Host 'cloud: skipped by request' -ForegroundColor Yellow
}
else {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $npm -or -not $npx) {
        Add-Result -Name 'cloud' -Status 'SKIP' -Detail 'npm/npx not on PATH'
        Write-Host 'cloud: npm not found on PATH, skipped' -ForegroundColor Yellow
    }
    else {
        foreach ($pkg in @(
            @{ Name = 'backend';  Path = $CloudBackend },
            @{ Name = 'frontend'; Path = $CloudFront }
        )) {
            if (-not (Test-Path -LiteralPath $pkg.Path)) {
                Add-Result -Name "cloud :: $($pkg.Name)" -Status 'SKIP' -Detail 'directory not found'
                continue
            }
            if (-not (Test-Path -LiteralPath (Join-Path $pkg.Path 'node_modules'))) {
                Invoke-NodeStep -Name "cloud :: $($pkg.Name) npm ci" `
                                -WorkingDirectory $pkg.Path `
                                -Executable 'npm' -Arguments @('ci')
            }
            Invoke-NodeStep -Name "cloud :: $($pkg.Name) tsc --noEmit" `
                            -WorkingDirectory $pkg.Path `
                            -Executable 'npx' -Arguments @('tsc', '--noEmit')
            Invoke-NodeStep -Name "cloud :: $($pkg.Name) test" `
                            -WorkingDirectory $pkg.Path `
                            -Executable 'npm' -Arguments @('test')
        }
    }
}

# --- summary -----------------------------------------------------------------
Write-Section 'Summary'
$script:Results | Format-Table -AutoSize | Out-String | Write-Host

$failed = @($script:Results | Where-Object { $_.Status -eq 'FAIL' })
$passed = @($script:Results | Where-Object { $_.Status -eq 'PASS' })
$skipped = @($script:Results | Where-Object { $_.Status -eq 'SKIP' })

Write-Host ("PASS={0}  FAIL={1}  SKIP={2}" -f $passed.Count, $failed.Count, $skipped.Count)

if ($failed.Count -gt 0) {
    Write-Host 'TEST_ALL_RESULT=FAIL' -ForegroundColor Red
    exit 1
}
Write-Host 'TEST_ALL_RESULT=PASS' -ForegroundColor Green
exit 0
