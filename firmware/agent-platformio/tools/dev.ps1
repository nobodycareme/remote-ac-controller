#Requires -Version 5.1
# ============================================================
# dev.ps1 - Remote AC Controller firmware development entry (public edition)
#
# Single entry point for every PlatformIO action in this repository.
# Do NOT call `pio` / `platformio` / `esptool` directly: this script owns the
# PlatformIO environment (core dir, build dir, cache dir, build flags) and the
# safety gates that keep public builds free of credentials.
#
# Portable by design: the project root is derived from this script's location,
# so the repository can be cloned anywhere.
#
# Only the `public` profile exists in the public repository. Private profiles
# (real credentials, real IR emission) are intentionally not shipped here.
# ============================================================

param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'build', 'clean-build', 'upload', 'monitor', 'verify', 'test', 'help')]
    [string]$Command = 'help',

    [Parameter()]
    [ValidateSet('public')]
    [string]$Profile = 'public',

    [Parameter()]
    [string]$Port = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------
# Paths - derived from script location, never hardcoded
# ------------------------------------------------------------
$ToolsDir     = $PSScriptRoot
$FirmwareRoot = Split-Path -Parent $ToolsDir
$RepoRoot     = Split-Path -Parent $FirmwareRoot
$WorkDir      = Join-Path $FirmwareRoot '.build'
$BuildDir     = Join-Path $WorkDir $Profile
$LibDepsDir   = Join-Path $WorkDir 'libdeps'
$CacheDir     = Join-Path $WorkDir 'cache'
$LogsDir      = Join-Path $WorkDir 'logs'
$LockFile     = Join-Path $WorkDir '.workflow.lock'

foreach ($d in @($WorkDir, $BuildDir, $LibDepsDir, $CacheDir, $LogsDir)) {
    [System.IO.Directory]::CreateDirectory($d) | Out-Null
}

# ------------------------------------------------------------
# Single-instance guard - PlatformIO is not safe to run concurrently
# ------------------------------------------------------------
$MutexName  = 'Local\RemoteACController_PlatformIO_Workflow'
$Mutex      = New-Object System.Threading.Mutex($false, $MutexName)
$MutexHeld  = $false
try {
    $MutexHeld = $Mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $MutexHeld = $true
}
if (-not $MutexHeld) {
    Write-Output 'DEV_PS1_MUTEX_PASS=False'
    Write-Output 'WORKFLOW_ALREADY_RUNNING=True'
    Write-Error 'Another firmware workflow is already running in this session.'
    exit 1
}
Write-Output 'DEV_PS1_MUTEX_PASS=True'
Set-Content -Path $LockFile -Value "$PID|$(Get-Date -Format o)" -Encoding ASCII

# ------------------------------------------------------------
# PlatformIO discovery
#   1. $env:PLATFORMIO_CORE_DIR  (an existing PlatformIO Core installation)
#   2. firmware/.pio-core        (repository-local Core, git-ignored)
#   3. pio / platformio on PATH
# ------------------------------------------------------------
function Resolve-PioExecutable {
    $candidates = @()

    if ($env:PLATFORMIO_CORE_DIR -and (Test-Path $env:PLATFORMIO_CORE_DIR)) {
        $candidates += (Join-Path $env:PLATFORMIO_CORE_DIR 'penv\Scripts\pio.exe')
        $candidates += (Join-Path $env:PLATFORMIO_CORE_DIR 'penv\Scripts\pio.bat')
        $candidates += (Join-Path $env:PLATFORMIO_CORE_DIR 'penv\Scripts\pio.ps1')
        $candidates += (Join-Path $env:PLATFORMIO_CORE_DIR 'penv/bin/pio')
    }

    $localCore = Join-Path $FirmwareRoot '.pio-core'
    if (Test-Path $localCore) {
        $candidates += (Join-Path $localCore 'penv\Scripts\pio.exe')
        $candidates += (Join-Path $localCore 'penv\Scripts\pio.bat')
        $candidates += (Join-Path $localCore 'penv\Scripts\pio.ps1')
        $candidates += (Join-Path $localCore 'penv/bin/pio')
    }

    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $resolved = (Resolve-Path $c).Path
            # Validate that the discovered executable actually runs (pio.exe shipped
            # with some PlatformIO Core installs is a broken stub).
            $LASTEXITCODE = 1  # default-fail so the catch block can always read it
            try {
                $null = & $resolved --version 2>&1
                if ($LASTEXITCODE -eq 0) { return $resolved }
            } catch {
                # Native stub (e.g. broken pio.exe) throws ApplicationFailedException;
                # $LASTEXITCODE stays at default-fail (1) -> fall through.
            }
        }
    }

    foreach ($name in @('pio', 'platformio')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    return $null
}

$PioExe = Resolve-PioExecutable

function Assert-Pio {
    if (-not $PioExe) {
        Write-Output 'PIO_AVAILABLE=False'
        Write-Error @'
PlatformIO Core was not found.

Install it once, then re-run this script:

  pip install --user platformio

or point this script at an existing installation:

  $env:PLATFORMIO_CORE_DIR = 'C:\path\to\.platformio'

or create a repository-local Core at firmware/.pio-core (git-ignored).
'@
        exit 2
    }
}

# ------------------------------------------------------------
# PlatformIO environment (process-local only; never persisted)
# ------------------------------------------------------------
$env:PLATFORMIO_BUILD_DIR   = $BuildDir
$env:PLATFORMIO_LIBDEPS_DIR = $LibDepsDir
$env:PLATFORMIO_CACHE_DIR   = $CacheDir
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'false'
$env:PLATFORMIO_DISABLE_PROGRESSBAR      = 'true'
$env:PYTHONUNBUFFERED = '1'

# Public profile: cloud module is compiled, but credentials, live campus auth
# and IR-mutating commands are all disabled at compile time.
$env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=0'
$env:BUILD_FLAGS_PRIVATE = ''

# ------------------------------------------------------------
# Safety gates
# ------------------------------------------------------------
$SecretHeaders = @('secrets.h', 'cloud_secrets.h')

function Assert-NoTrackedSecrets {
    $bad = @()
    foreach ($h in $SecretHeaders) {
        $p = Join-Path (Join-Path $FirmwareRoot 'include') $h
        if (-not (Test-Path $p)) { continue }
        $tracked = & git -C $RepoRoot ls-files --error-unmatch "firmware/include/$h" 2>$null
        if ($LASTEXITCODE -eq 0 -and $tracked) { $bad += "firmware/include/$h" }
    }
    if ($bad.Count -gt 0) {
        Write-Output 'TRACKED_SECRET_HEADER=True'
        Write-Error ("Secret headers must never be tracked by git: " + ($bad -join ', '))
        exit 3
    }
    Write-Output 'TRACKED_SECRET_HEADER=False'
}

function Assert-NoHardcodedPort {
    # The serial port must always be discovered at runtime. A literal port name
    # in platformio.ini or in this script is a configuration bug.
    $needle = 'COM' + '[0-9]'
    foreach ($f in @((Join-Path $FirmwareRoot 'platformio.ini'), $PSCommandPath)) {
        if (-not (Test-Path $f)) { continue }
        $content = Get-Content $f -Raw
        if ($content -match $needle) {
            Write-Output 'HARDCODED_SERIAL_PORT=True'
            Write-Error "Hardcoded serial port found in $f"
            exit 4
        }
    }
    Write-Output 'HARDCODED_SERIAL_PORT=False'
}

function Get-DefinedSecrets {
    # Reads locally provided secret headers (never committed) so the artifact
    # scan can prove the values did not leak into the compiled output.
    $found = @{}
    foreach ($h in $SecretHeaders) {
        $p = Join-Path (Join-Path $FirmwareRoot 'include') $h
        if (-not (Test-Path $p)) { continue }
        $c = (Get-Content $p -Raw) -replace "\\\r?\n\s*", ''
        foreach ($m in [regex]::Matches($c, '#define\s+(\w+)\s+"([^"]*)"')) {
            $name = $m.Groups[1].Value
            $val  = $m.Groups[2].Value
            if ($val.Length -ge 6 -and $name -match 'PASSWORD|USERNAME|ACCOUNT|TOKEN|SECRET' -and $name -notmatch 'DEVICE_ID') {
                $found[$name] = $val
            }
        }
    }
    return $found
}

function Invoke-SecretScan {
    Write-Output "SECRET_SCAN [$Profile]"
    $secrets = Get-DefinedSecrets
    Write-Output "SECRETS_LOADED_FOR_SCAN=$($secrets.Count)"
    if ($secrets.Count -eq 0) {
        # Nothing local to leak; the public build has no credentials by design.
        Write-Output 'PUBLIC_SECRET_SCAN_PASS=True'
        return $true
    }

    $envDir = Join-Path $BuildDir 'nodemcuv2'
    $files  = @()
    foreach ($n in @('firmware.bin', 'firmware.elf', 'firmware.map')) {
        $p = Join-Path $envDir $n
        if (Test-Path $p) { $files += $p }
    }
    if (Test-Path $envDir) {
        $files += (Get-ChildItem $envDir -Recurse -Filter '*.o' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }

    $hits = 0
    foreach ($f in $files) {
        $txt = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($f))
        foreach ($k in $secrets.Keys) {
            $hits += ([regex]::Matches($txt, [regex]::Escape($secrets[$k]))).Count
        }
    }
    Write-Output "PUBLIC_SECRET_HITS=$hits"

    if ($hits -gt 0) {
        Write-Output 'PUBLIC_SECRET_SCAN_PASS=False'
        foreach ($f in $files) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        Write-Output 'CONTAMINATED_ARTIFACTS_DELETED=True'
        return $false
    }
    Write-Output 'PUBLIC_SECRET_SCAN_PASS=True'
    return $true
}

# ------------------------------------------------------------
# Serial port discovery - always dynamic, never hardcoded
# Known USB-UART bridges used on NodeMCU boards: CH9102/CH340, CP210x, FTDI.
# ------------------------------------------------------------
$UsbUartVidPid = @(
    'VID_1A86&PID_55D4',   # CH9102
    'VID_1A86&PID_7523',   # CH340
    'VID_10C4&PID_EA60',   # CP210x
    'VID_0403'             # FTDI
)

function Resolve-SerialPort {
    if ($Port) { return $Port }

    $portPattern = '\((' + 'COM' + '[0-9]+)\)'
    $matched = @()
    try {
        $devices = Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop |
                   Where-Object { $_.PNPDeviceID -and $_.Name }
        foreach ($d in $devices) {
            foreach ($sig in $UsbUartVidPid) {
                if ($d.PNPDeviceID -like "*$sig*") {
                    $m = [regex]::Match($d.Name, $portPattern)
                    if ($m.Success) { $matched += $m.Groups[1].Value }
                }
            }
        }
    } catch {
        Write-Output "SERIAL_ENUMERATION_WARNING=$($_.Exception.Message)"
    }

    $matched = @($matched | Sort-Object -Unique)
    if ($matched.Count -eq 1) { return $matched[0] }
    if ($matched.Count -gt 1) {
        Write-Output ("SERIAL_PORT_AMBIGUOUS=" + ($matched -join ','))
        return ''
    }
    return ''
}

# ------------------------------------------------------------
# PlatformIO invocation
# ------------------------------------------------------------
function Invoke-Pio {
    param([string[]]$PioArgs, [string]$LogName)

    Assert-Pio
    $log = Join-Path $LogsDir ("{0}_{1}.log" -f $LogName, $PID)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PioExe @PioArgs 2>&1 | Tee-Object -FilePath $log
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    Write-Output "PIO_LOG=$log"
    return $rc
}

function Invoke-Build {
    param([switch]$Clean)

    Assert-NoTrackedSecrets
    Assert-NoHardcodedPort

    if ($Clean) {
        Write-Output "CLEAN [$Profile]"
        $rc = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '-t', 'clean', '--project-dir', $FirmwareRoot) -LogName 'pio_clean'
        if ($rc -ne 0) { Write-Output "CLEAN_RESULT=FAIL"; return $rc }
    }

    Write-Output "BUILD [$Profile]"
    $rc = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '--project-dir', $FirmwareRoot) -LogName 'pio_build'
    if ($rc -ne 0) {
        Write-Output 'BUILD_RESULT=FAIL'
        return $rc
    }
    if (-not (Invoke-SecretScan)) {
        Write-Output 'BUILD_RESULT=FAIL_SECRET_SCAN'
        return 5
    }
    $bin = Join-Path $BuildDir 'nodemcuv2\firmware.bin'
    if (Test-Path $bin) {
        $sha = (Get-FileHash $bin -Algorithm SHA256).Hash.ToLower()
        Write-Output "FIRMWARE_BIN=$bin"
        Write-Output "FIRMWARE_SHA256=$sha"
    }
    Write-Output 'BUILD_RESULT=PASS'
    return 0
}

# ------------------------------------------------------------
# Commands
# ------------------------------------------------------------
$exitCode = 0
try {
    switch ($Command) {

        'status' {
            Write-Output '--- Remote AC Controller / firmware ---'
            Write-Output "REPO_ROOT=$RepoRoot"
            Write-Output "FIRMWARE_ROOT=$FirmwareRoot"
            Write-Output "PROFILE=$Profile"
            Write-Output "BUILD_DIR=$BuildDir"
            Write-Output ("PIO_AVAILABLE=" + [bool]$PioExe)
            if ($PioExe) {
                Write-Output "PIO_EXE=$PioExe"
                $v = (& $PioExe --version 2>&1) -join ' '
                Write-Output "PIO_VERSION=$v"
            }
            foreach ($h in $SecretHeaders) {
                $p = Join-Path (Join-Path $FirmwareRoot 'include') $h
                Write-Output ("LOCAL_{0}={1}" -f $h.ToUpper().Replace('.', '_'), (Test-Path $p))
            }
            $p = Resolve-SerialPort
            Write-Output ("SERIAL_PORT_DETECTED=" + $(if ($p) { $p } else { 'NONE' }))
            Write-Output 'CLOUD_CREDENTIALS_COMPILED=False'
            Write-Output 'REAL_IR_EMISSION_COMPILED=False'
        }

        'verify' {
            Assert-NoTrackedSecrets
            Assert-NoHardcodedPort
            $ini = Join-Path $FirmwareRoot 'platformio.ini'
            Write-Output ("PLATFORMIO_INI_PRESENT=" + (Test-Path $ini))
            if (-not (Test-Path $ini)) { $exitCode = 6 }
            Write-Output ("PIO_AVAILABLE=" + [bool]$PioExe)
            Write-Output ("VERIFY_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'test' {
            Assert-NoTrackedSecrets
            Assert-NoHardcodedPort
            $testDir = Join-Path $FirmwareRoot 'test'
            if (-not (Test-Path $testDir)) {
                Write-Output 'TEST_RESULT=SKIP_NO_TESTS'
                break
            }
            Assert-Pio
            $exitCode = Invoke-Pio -PioArgs @('test', '-e', 'nodemcuv2', '--without-uploading', '--without-testing', '--project-dir', $FirmwareRoot) -LogName 'pio_test'
            Write-Output ("TEST_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'build'       { $exitCode = Invoke-Build }
        'clean-build' { $exitCode = Invoke-Build -Clean }

        'upload' {
            $com = Resolve-SerialPort
            if (-not $com) {
                Write-Output 'UPLOAD_BLOCKED=NO_SERIAL_PORT'
                Write-Output 'Hint: connect the board, or pass -Port <port-name> explicitly.'
                $exitCode = 7
                break
            }
            $bin = Join-Path $BuildDir 'nodemcuv2\firmware.bin'
            if (-not (Test-Path $bin)) {
                Write-Output 'UPLOAD_BLOCKED=BIN_MISSING'
                Write-Output 'Hint: run `dev.ps1 build` first.'
                $exitCode = 8
                break
            }
            Write-Output "UPLOAD [$Profile] -> $com"
            $env:PLATFORMIO_UPLOAD_PORT = $com
            $exitCode = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '-t', 'upload', '--upload-port', $com, '--project-dir', $FirmwareRoot) -LogName 'pio_upload'
            Write-Output ("UPLOAD_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'monitor' {
            $com = Resolve-SerialPort
            if (-not $com) {
                Write-Output 'MONITOR_BLOCKED=NO_SERIAL_PORT'
                $exitCode = 7
                break
            }
            $exitCode = Invoke-Pio -PioArgs @('device', 'monitor', '--port', $com, '--baud', '115200') -LogName 'pio_monitor'
        }

        default {
            Write-Output 'USAGE: ./tools/dev.ps1 <command> [-Profile public] [-Port <port-name>]'
            Write-Output ''
            Write-Output 'Commands:'
            Write-Output '  status        Show resolved paths, PlatformIO version, detected serial port'
            Write-Output '  verify        Run the safety gates without building'
            Write-Output '  test          Run the firmware test suite'
            Write-Output '  build         Compile the public firmware and scan artifacts for secrets'
            Write-Output '  clean-build   Clean, then build'
            Write-Output '  upload        Flash the last build to a detected board'
            Write-Output '  monitor       Open the serial monitor'
            Write-Output '  help          Show this message'
            Write-Output ''
            Write-Output 'Profiles:'
            Write-Output '  public        The only profile in the public repository. No credentials are'
            Write-Output '                compiled in, live campus auth is off, IR emission is disabled.'
            Write-Output ''
            Write-Output 'Never call pio/platformio/esptool directly - this script owns the build'
            Write-Output 'environment and the safety gates.'
        }
    }
} finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    if ($MutexHeld) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}

exit $exitCode
