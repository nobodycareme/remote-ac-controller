#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the IR Simple Learner Windows x64 EXE from source.

.DESCRIPTION
    Creates a Python virtual environment, installs dependencies, and runs
    PyInstaller to produce a standalone Windows executable.

    The output file is named:
        IR_Simple_Learner_v<VERSION>_windows_x64.exe

    This script:
      * Never uploads, flashes, or opens a serial port.
      * Never touches production credentials or capture data.
      * Only builds from 'requirements.txt' inside this directory.

.EXAMPLE
    pwsh tools/ir-simple-learner/build.ps1

.EXAMPLE
    pwsh tools/ir-simple-learner/build.ps1 -Clean
#>
[CmdletBinding()]
param(
    [switch] $Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- constants ---------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$SrcDir      = Join-Path $ScriptDir 'src'
$VenvDir     = Join-Path $ScriptDir '.venv'
$VersionFile = Join-Path $ScriptDir 'VERSION'
$ReqFile     = Join-Path $ScriptDir 'requirements.txt'
$LockFile    = Join-Path $ScriptDir 'requirements-lock.txt'
$OutDir      = Join-Path $ScriptDir 'dist'

if (-not (Test-Path -LiteralPath $VersionFile)) {
    throw "VERSION file not found at $VersionFile"
}
$Version = (Get-Content -LiteralPath $VersionFile -Raw).Trim()
if ([string]::IsNullOrEmpty($Version)) {
    throw 'VERSION file is empty'
}
$ExeName = "IR_Simple_Learner_v${Version}_windows_x64.exe"
$ExePath = Join-Path $OutDir $ExeName

# --- helpers -----------------------------------------------------------------
function Write-Step {
    param([string] $Title)
    Write-Host ''
    Write-Host ('-' * 60) -ForegroundColor DarkGray
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ('-' * 60) -ForegroundColor DarkGray
}

# --- guards ------------------------------------------------------------------
if (Test-Path -LiteralPath (Join-Path $RepoRoot 'Private')) {
    throw 'GUARD_FAIL: a Private/ directory exists in the repository.'
}

if (-not (Test-Path -LiteralPath (Join-Path $SrcDir 'simple_ir_learner.py'))) {
    throw "simple_ir_learner.py not found at $SrcDir"
}

Write-Host ''
Write-Host 'IR Simple Learner build' -ForegroundColor White
Write-Host "repository  : $RepoRoot"
Write-Host "source      : $SrcDir"
Write-Host "version     : v$Version"
Write-Host "output      : $ExeName"
Write-Host "started     : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- clean -------------------------------------------------------------------
if ($Clean) {
    Write-Step 'Clean build artefacts'
    if (Test-Path -LiteralPath $VenvDir) {
        Remove-Item -Recurse -Force -LiteralPath $VenvDir
        Write-Host 'Removed .venv/'
    }
    if (Test-Path -LiteralPath $OutDir) {
        Remove-Item -Recurse -Force -LiteralPath $OutDir
        Write-Host 'Removed dist/'
    }
    $pycache = Join-Path $SrcDir '__pycache__'
    if (Test-Path -LiteralPath $pycache) {
        Remove-Item -Recurse -Force -LiteralPath $pycache
        Write-Host 'Removed __pycache__/'
    }
    $buildDir = Join-Path $ScriptDir 'build'
    if (Test-Path -LiteralPath $buildDir) {
        Remove-Item -Recurse -Force -LiteralPath $buildDir
        Write-Host 'Removed build/'
    }
}

# --- python detection --------------------------------------------------------
Write-Step 'Detect Python'
$pythonCandidates = @()

# 1. Explicit environment variable
if ($env:IR_PYTHON -and (Test-Path -LiteralPath $env:IR_PYTHON)) {
    $pythonCandidates += $env:IR_PYTHON
}
# 2. System PATH
foreach ($p in @('python3.exe', 'python.exe')) {
    $found = Get-Command $p -ErrorAction SilentlyContinue
    if ($found) {
        $pythonCandidates += $found.Source
    }
}

if ($pythonCandidates.Count -eq 0) {
    throw 'Python not found. Install Python 3.9+ and add it to PATH.'
}

$PythonExe = $pythonCandidates[0]
Write-Host "Using: $PythonExe"

$pyVer = & $PythonExe --version 2>&1
Write-Host "Version: $pyVer"

# --- venv --------------------------------------------------------------------
Write-Step 'Create virtual environment'
$buildVenv = $false
if (-not (Test-Path -LiteralPath $VenvDir)) {
    $buildVenv = $true
}
if ($buildVenv) {
    Write-Host "Creating venv at $VenvDir ..."
    & $PythonExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "venv python.exe not found: $VenvPython"
}

# --- install dependencies ----------------------------------------------------
Write-Step 'Install dependencies'
$useLock = Test-Path -LiteralPath $LockFile
$installTarget = if ($useLock) { $LockFile } else { $ReqFile }
Write-Host "Installing from: $installTarget"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $VenvPython -m pip install -r $installTarget
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }

Write-Host ''
Write-Host 'Installed packages:' -ForegroundColor DarkGray
& $VenvPython -m pip list --format=columns

# --- build -------------------------------------------------------------------
Write-Step 'Run PyInstaller'

$PyInstaller = Join-Path $VenvDir 'Scripts\pyinstaller.exe'
if (-not (Test-Path -LiteralPath $PyInstaller)) {
    throw "pyinstaller.exe not found at $PyInstaller"
}

$MainScript = Join-Path $SrcDir 'simple_ir_learner.py'

# Build from the src directory so local imports work
Push-Location -LiteralPath $SrcDir
try {
    & $PyInstaller `
        --onefile `
        --windowed `
        --name $ExeName.Replace('.exe', '') `
        --distpath $OutDir `
        --workpath (Join-Path $ScriptDir 'build') `
        --specpath $ScriptDir `
        --clean `
        $MainScript

    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

# Verify output
if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Expected EXE not found: $ExePath"
}

# Compute SHA256
$FileInfo = Get-Item -LiteralPath $ExePath
$Sha256 = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLower()
$SizeBytes = $FileInfo.Length
$SizeMB = "{0:N1}" -f ($SizeBytes / 1MB)

Write-Host ''
Write-Host 'Build complete' -ForegroundColor Green
Write-Host "  File   : $ExePath"
Write-Host "  Size   : $SizeBytes bytes ($SizeMB MB)"
Write-Host "  SHA256 : $Sha256"
Write-Host "finished : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host 'BUILD_RESULT=PASS' -ForegroundColor Green
exit 0
