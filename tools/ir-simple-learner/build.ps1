#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the IR Simple Learner Windows x64 EXE from source.

.DESCRIPTION
    Creates a Python 3.12 virtual environment, installs the pinned
    requirements-lock.txt, runs the unit tests, and builds the standalone
    Windows executable with PyInstaller.

    The output file is named:
        IR_Simple_Learner_v<VERSION>_windows_x64.exe

    This script:
      * Never uploads, flashes, or opens a serial port.
      * Never touches production credentials or capture data.
      * Installs ONLY from 'requirements-lock.txt' (no fallback to
        requirements.txt when the lock file is present).
      * Runs the source unit tests and the EXE --self-test as gates.

.PARAMETER Clean
    Remove .venv/, dist/, build/, *.spec, and __pycache__ first.

.PARAMETER PythonPath
    Explicit path to the python.exe to use (CI passes the
    actions/setup-python Python here). When omitted, the script probes
    IR_PYTHON env, python3.exe, and python.exe.

.EXAMPLE
    pwsh tools/ir-simple-learner/build.ps1 -Clean

.EXAMPLE
    pwsh tools/ir-simple-learner/build.ps1 -Clean -PythonPath "C:\Python312\python.exe"
#>
[CmdletBinding()]
param(
    [switch] $Clean,
    [string] $PythonPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- constants ---------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$SrcDir      = Join-Path $ScriptDir 'src'
$TestsDir    = Join-Path $SrcDir 'tests'
$VenvDir     = Join-Path $ScriptDir '.venv'
$VersionFile = Join-Path $ScriptDir 'VERSION'
$LockFile    = Join-Path $ScriptDir 'requirements-lock.txt'
$OutDir      = Join-Path $ScriptDir 'dist'
$BuildDir    = Join-Path $ScriptDir 'build'
$SpecDir     = Join-Path $ScriptDir 'spec-tmp'

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

function Invoke-Native {
    <#
        Runs a native process, streams stdout/stderr to the console, and
        throws when the process ExitCode is non-zero. stderr text alone
        (e.g. PyInstaller INFO logs) NEVER causes a failure; only the exit
        code decides, so PowerShell 5.1's $ErrorActionPreference='Stop'
        cannot turn normal stderr into a terminating error.
    #>
    param(
        [Parameter(Mandatory)][string] $FilePath,
        [string[]] $ArgumentList = @()
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    # PS 5.1 has no ProcessStartInfo.ArgumentList; quote each argument manually.
    $quoted = @()
    foreach ($a in $ArgumentList) {
        $quoted += '"' + $a.Replace('"', '\"') + '"'
    }
    $psi.Arguments = $quoted -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $outBuilder = New-Object System.Text.StringBuilder
    $errBuilder = New-Object System.Text.StringBuilder
    $outEvent = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action {
        if ($EventArgs.Data -ne $null) {
            Write-Host $EventArgs.Data
            [void]$Event.MessageData.AppendLine($EventArgs.Data)
        }
    } -MessageData $outBuilder
    $errEvent = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action {
        if ($EventArgs.Data -ne $null) {
            Write-Host $EventArgs.Data
            [void]$Event.MessageData.AppendLine($EventArgs.Data)
        }
    } -MessageData $errBuilder

    try {
        [void]$proc.Start()
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()
        $proc.WaitForExit()
        $proc.WaitForExit()  # ensure async handlers flushed
    }
    finally {
        Unregister-Event -SourceIdentifier $outEvent.Name -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $errEvent.Name -ErrorAction SilentlyContinue
    }

    $code = $proc.ExitCode
    if ($code -ne 0) {
        $tail = $errBuilder.ToString()
        if ($tail.Length -gt 300) { $tail = $tail.Substring($tail.Length - 300) }
        throw "command failed (exit code $code): $FilePath $($ArgumentList -join ' ')$([Environment]::NewLine)$tail"
    }
    return $outBuilder.ToString()
}

# --- guards ------------------------------------------------------------------
if (Test-Path -LiteralPath (Join-Path $RepoRoot 'Private')) {
    throw 'GUARD_FAIL: a Private/ directory exists in the repository.'
}

if (-not (Test-Path -LiteralPath (Join-Path $SrcDir 'simple_ir_learner.py'))) {
    throw "simple_ir_learner.py not found at $SrcDir"
}

if (-not (Test-Path -LiteralPath $LockFile)) {
    throw "requirements-lock.txt not found at $LockFile — the official build requires the pinned lock file."
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
    foreach ($p in @($VenvDir, $OutDir, $BuildDir, $SpecDir)) {
        if (Test-Path -LiteralPath $p) {
            Remove-Item -Recurse -Force -LiteralPath $p
            Write-Host "Removed $(Split-Path -Leaf $p)/"
        }
    }
    Get-ChildItem -LiteralPath $ScriptDir -Filter '*.spec' -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Force -LiteralPath $_.FullName; Write-Host "Removed $($_.Name)" }
    $pycache = Join-Path $SrcDir '__pycache__'
    if (Test-Path -LiteralPath $pycache) {
        Remove-Item -Recurse -Force -LiteralPath $pycache
        Write-Host 'Removed __pycache__/'
    }
}

# --- python detection --------------------------------------------------------
Write-Step 'Detect Python'
$pythonCandidates = @()
if ($PythonPath -and (Test-Path -LiteralPath $PythonPath)) {
    $pythonCandidates += $PythonPath
}
if ($env:IR_PYTHON -and (Test-Path -LiteralPath $env:IR_PYTHON)) {
    $pythonCandidates += $env:IR_PYTHON
}
foreach ($p in @('python3.exe', 'python.exe')) {
    $found = Get-Command $p -ErrorAction SilentlyContinue
    if ($found) { $pythonCandidates += $found.Source }
}

if ($pythonCandidates.Count -eq 0) {
    throw 'Python not found. Pass -PythonPath <python.exe> or add Python 3.12 x64 to PATH.'
}
$PythonExe = $pythonCandidates[0]
Write-Host "Using: $PythonExe"
Invoke-Native -FilePath $PythonExe -ArgumentList @('--version')

# --- python 3.12 + tkinter gate ----------------------------------------------
$pyVerOut = Invoke-Native -FilePath $PythonExe -ArgumentList @('-c',
    'import sys; print("%d.%d" % sys.version_info[:2])')
$pyMajorMinor = ($pyVerOut | Out-String).Trim()
Write-Host "Python version: $pyMajorMinor"
if ($pyMajorMinor -notmatch '^3\.12(\.|$)') {
    throw "Python 3.12 x64 is required for the official build; found $pyMajorMinor. Pass -PythonPath to a Python 3.12 interpreter."
}
Invoke-Native -FilePath $PythonExe -ArgumentList @('-c',
    'import tkinter; print("Tk", tkinter.TkVersion)')

# --- venv --------------------------------------------------------------------
Write-Step 'Create virtual environment'
$buildVenv = $false
if (-not (Test-Path -LiteralPath $VenvDir)) { $buildVenv = $true }
if ($buildVenv) {
    Write-Host "Creating venv at $VenvDir ..."
    Invoke-Native -FilePath $PythonExe -ArgumentList @('-m', 'venv', $VenvDir)
}

$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "venv python.exe not found: $VenvPython"
}

# --- install dependencies (strict lock, no fallback) -------------------------
Write-Step 'Install dependencies'
Write-Host "Installing from: $LockFile"
Invoke-Native -FilePath $VenvPython -ArgumentList @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-Native -FilePath $VenvPython -ArgumentList @('-m', 'pip', 'install', '--require-hashes', '-r', $LockFile)
Invoke-Native -FilePath $VenvPython -ArgumentList @('-m', 'pip', 'list', '--format=columns')

# --- unit tests (source) -----------------------------------------------------
Write-Step 'Run unit tests'
Invoke-Native -FilePath $VenvPython -ArgumentList @('-m', 'unittest', 'discover', '-s', $TestsDir, '-p', 'test_*.py', '-v')

# --- build -------------------------------------------------------------------
Write-Step 'Run PyInstaller'
$MainScript = Join-Path $SrcDir 'simple_ir_learner.py'
Push-Location -LiteralPath $SrcDir
try {
    Invoke-Native -FilePath $VenvPython -ArgumentList @(
        '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', $ExeName.Replace('.exe', ''),
        '--distpath', $OutDir,
        '--workpath', $BuildDir,
        '--specpath', $SpecDir,
        '--clean',
        $MainScript)
}
finally {
    Pop-Location
}

# --- verify output -----------------------------------------------------------
if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Expected EXE not found: $ExePath"
}

$FileInfo = Get-Item -LiteralPath $ExePath
$Sha256 = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLower()
$SizeBytes = $FileInfo.Length
$SizeMB = "{0:N1}" -f ($SizeBytes / 1MB)

# --- EXE self-test -----------------------------------------------------------
Write-Step 'EXE self-test'
# The EXE is --windowed: PowerShell does NOT wait for it with the call
# operator, so use Start-Process -Wait to obtain the real exit code.
$reportPath = Join-Path $OutDir 'ir_learner_self_test.txt'
if (Test-Path -LiteralPath $reportPath) {
    Remove-Item -Force -LiteralPath $reportPath
}
$selfProc = Start-Process -FilePath $ExePath -ArgumentList '--self-test' -Wait -PassThru
$selfTestCode = $selfProc.ExitCode
if (-not (Test-Path -LiteralPath $reportPath)) {
    throw "EXE self-test report not found: $reportPath"
}
Write-Host ''
Write-Host ("SELF_TEST_EXIT_CODE=" + $selfTestCode)
Get-Content -LiteralPath $reportPath | ForEach-Object { Write-Host "  $_" }
if ($selfTestCode -ne 0) {
    throw "EXE --self-test failed with exit code $selfTestCode"
}
if (-not (Select-String -LiteralPath $reportPath -Pattern '^IR_LEARNER_SELF_TEST_PASS=True' -Quiet)) {
    throw 'EXE --self-test report does not contain IR_LEARNER_SELF_TEST_PASS=True'
}

Write-Host ''
Write-Host 'Build complete' -ForegroundColor Green
Write-Host "  File   : $ExePath"
Write-Host "  Size   : $SizeBytes bytes ($SizeMB MB)"
Write-Host "  SHA256 : $Sha256"
Write-Host "  SelfTest: PASS"
Write-Host "finished : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host 'BUILD_RESULT=PASS' -ForegroundColor Green
exit 0
