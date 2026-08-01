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
# The public repository ships the `public` profile plus two open example
# profiles. Private profiles (real credentials, real IR emission) are
# intentionally not shipped here.
# ============================================================

param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'build', 'clean-build', 'upload', 'monitor', 'verify', 'test', 'help')]
    [string]$Command = 'help',

    [Parameter()]
    [ValidateSet('public', 'local-campus-example', 'public-cloud-example',
                 'local-wifi', 'local-wifi-cloud')]
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
    # Each candidate carries the Core directory it belongs to, so that the caller
    # can pin $env:PLATFORMIO_CORE_DIR to the same installation. Without this the
    # resolved executable would still fall back to the user-global ~/.platformio
    # Core and re-download every toolchain package.
    $candidates = @()
    $addCore = {
        param($coreDir)
        foreach ($rel in @('penv\Scripts\pio.exe', 'penv\Scripts\pio.bat', 'penv\Scripts\pio.ps1', 'penv/bin/pio')) {
            $script:PioCandidates += [pscustomobject]@{
                Path    = (Join-Path $coreDir $rel)
                CoreDir = $coreDir
            }
        }
    }
    $script:PioCandidates = @()

    if ($env:PLATFORMIO_CORE_DIR -and (Test-Path $env:PLATFORMIO_CORE_DIR)) {
        & $addCore (Resolve-Path $env:PLATFORMIO_CORE_DIR).Path
    }

    $localCore = Join-Path $FirmwareRoot '.pio-core'
    if (Test-Path $localCore) {
        & $addCore (Resolve-Path $localCore).Path
    }

    # Project-local config: .pio-core-dir in the firmware root (one-line path,
    # git-ignored, mirrors the $env:PLATFORMIO_CORE_DIR behaviour).
    # Read with -Encoding UTF8 so paths containing non-ASCII characters are preserved.
    $configFile = Join-Path $RepoRoot '.pio-core-dir'
    if (Test-Path $configFile) {
        $corePath = (Get-Content -Path $configFile -TotalCount 1 -Encoding UTF8).Trim()
        if ($corePath -and (Test-Path $corePath)) {
            & $addCore (Resolve-Path $corePath).Path
        }
    }

    $candidates = $script:PioCandidates
    foreach ($c in $candidates) {
        if ($c.Path -and (Test-Path $c.Path)) {
            # Skip the broken pio.exe stub (some PlatformIO Core installs ship a
            # placeholder that always fails with "not valid for this OS").
            if ($c.Path -like '*pio.exe') { continue }
            $resolved = (Resolve-Path $c.Path).Path
            # Validate that the discovered executable actually runs.
            $ErrorActionPreference = 'Continue'
            $null = & $resolved --version 2>&1
            $rc = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($rc -eq 0) {
                $script:ResolvedPioCoreDir = $c.CoreDir
                return $resolved
            }
        }
    }

    foreach ($name in @('pio', 'platformio')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    return $null
}

$script:ResolvedPioCoreDir = $null
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
# Pin the Core directory to the installation the executable was discovered in.
# Otherwise PlatformIO silently falls back to the user-global ~/.platformio and
# re-downloads every toolchain package on the first build.
if ($script:ResolvedPioCoreDir) {
    $env:PLATFORMIO_CORE_DIR = $script:ResolvedPioCoreDir
}
$env:PLATFORMIO_BUILD_DIR   = $BuildDir
$env:PLATFORMIO_LIBDEPS_DIR = $LibDepsDir
$env:PLATFORMIO_CACHE_DIR   = $CacheDir
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'false'
$env:PLATFORMIO_DISABLE_PROGRESSBAR      = 'true'
$env:PYTHONUNBUFFERED = '1'

# Public profile: cloud module is compiled, but credentials, live campus auth
# and IR-mutating commands are all disabled at compile time.
switch ($Profile) {
  'local-campus-example' {
    # Open example of the Xidian campus profile: compiles campus auth + srun-c,
    # but live auth is OFF (no credentials) and IR emission is disabled. The
    # profile is the public, non-secret Xidian example (profiles/xidian.example.h).
    # ENABLE_AUTO_CAMPUS_AUTH stays 0 in every PUBLIC build (v1.2.0 feature-gate
    # rule): unattended auth is only legal in a PRIVATE build with
    # ENABLE_CONTROLLED_LIVE_AUTH=1, and feature_gates.h turns the AUTO=1+LIVE=0
    # combination into a hard #error rather than a silent no-op.
    # CAMPUS_PROFILE_HEADER is consumed by `#include CAMPUS_PROFILE_HEADER`, so
    # the macro body must still carry its double quotes when it reaches the
    # compiler. PlatformIO strips one level of quoting from build_flags, hence
    # the backslash escapes (the documented -D NAME=\"VALUE\" idiom). Without
    # them the preprocessor reports: #include expects "FILENAME" or <FILENAME>.
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=0 -DENABLE_CLOUD_CREDENTIALS=0 -DENABLE_CAMPUS_AUTH=1 -DENABLE_AUTO_CAMPUS_AUTH=0 -DCAMPUS_PROFILE_HEADER=\"profiles/xidian.example.h\"'
  }
  'public-cloud-example' {
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=0'
  }
  'local-wifi' {
    # Home/lab WPA/WPA2 with compiled-in credentials (wifi_secrets.h) and
    # unattended connect at boot. Cloud/campus auth stay off.
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=0 -DENABLE_CLOUD_CREDENTIALS=0 -DENABLE_CAMPUS_AUTH=0 -DENABLE_WIFI_CREDENTIALS=1 -DENABLE_AUTO_WIFI_CONNECT=1'
  }
  'local-wifi-cloud' {
    # local-wifi + cloud transport. Cloud consumes the same WPA link.
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=0 -DENABLE_CAMPUS_AUTH=0 -DENABLE_WIFI_CREDENTIALS=1 -DENABLE_AUTO_WIFI_CONNECT=1'
  }
  default {
    # public: cloud module compiled, credentials/live campus auth/IR-mutating off.
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=0'
  }
}
$env:BUILD_FLAGS_PRIVATE = ''

# ------------------------------------------------------------
# local-wifi profiles require the untracked wifi_secrets.h file
# ------------------------------------------------------------
if ($Profile -in @('local-wifi', 'local-wifi-cloud')) {
    $WifiSecrets = Join-Path $RepoRoot 'shared/RemoteACCore/src/config/wifi_secrets.h'
    if (-not (Test-Path -LiteralPath $WifiSecrets)) {
        Write-Output 'WIFI_SECRETS_MISSING=True'
        Write-Output 'Copy firmware/shared/RemoteACCore/src/config/wifi_secrets.example.h to'
        Write-Output 'firmware/shared/RemoteACCore/src/config/wifi_secrets.h and fill in your'
        Write-Output 'router SSID and password. The real file is git-ignored.'
        exit 5
    }
    Write-Output 'WIFI_SECRETS_PRESENT=True'
}

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
    $previousPreference = $ErrorActionPreference

    try {
        # Native stdout/stderr are merged, written to the log file, and mirrored to
        # the host (console) stream only. They are deliberately kept OFF the success
        # stream so the function's return value stays a single, strongly-typed result
        # object. Letting build output flow into the return value previously produced an
        # Object[] whose element-wise `-ne 0` comparison always evaluated as FAIL
        # (false negative) even when the native process exited 0.
        $ErrorActionPreference = 'Continue'
        & $PioExe @PioArgs 2>&1 |
            Tee-Object -FilePath $log |
            ForEach-Object { Write-Host $_ }
        $nativeExitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        ExitCode = $nativeExitCode
        LogPath  = $log
    }
}

# Publishes its exit code via $script:LastRc instead of returning it: the
# BUILD_RESULT=/FIRMWARE_SHA256= contract lines go to the success stream, so an
# `$rc = Invoke-Build` assignment would swallow them into the return value.
function Invoke-Build {
    param([switch]$Clean)

    $script:LastRc = 0
    Assert-NoTrackedSecrets
    Assert-NoHardcodedPort

    if ($Clean) {
        Write-Output "CLEAN [$Profile]"
        $result = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '-t', 'clean', '--project-dir', $FirmwareRoot) -LogName 'pio_clean'
        Write-Output ("PIO_LOG=" + $result.LogPath)
        $rc = [int]$result.ExitCode
        if ($rc -ne 0) { Write-Output "CLEAN_RESULT=FAIL"; $script:LastRc = $rc; return }
    }

    Write-Output "BUILD [$Profile]"
    $result = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '--project-dir', $FirmwareRoot) -LogName 'pio_build'
    Write-Output ("PIO_LOG=" + $result.LogPath)
    $rc = [int]$result.ExitCode
    if ($rc -ne 0) {
        Write-Output 'BUILD_RESULT=FAIL'
        $script:LastRc = $rc
        return
    }
    if (-not (Invoke-SecretScan)) {
        Write-Output 'BUILD_RESULT=FAIL_SECRET_SCAN'
        $script:LastRc = 5
        return
    }
    $bin = Join-Path $BuildDir 'nodemcuv2\firmware.bin'
    if (Test-Path $bin) {
        $sha = (Get-FileHash $bin -Algorithm SHA256).Hash.ToLower()
        Write-Output "FIRMWARE_BIN=$bin"
        Write-Output "FIRMWARE_SHA256=$sha"
    }
    Write-Output 'BUILD_RESULT=PASS'
    $script:LastRc = 0
}

# ------------------------------------------------------------
# Commands
# ------------------------------------------------------------
$exitCode = 0
$script:LastRc = 0
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
                Write-Output "PIO_CORE_DIR=$env:PLATFORMIO_CORE_DIR"
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
            # This command is a STATIC safety gate only: it confirms the config file
            # exists, PlatformIO is discoverable, no secret headers are tracked, and no
            # serial port is hardcoded. It does NOT recompile the firmware or run it on
            # a device, so it must not be reported as a runtime/dynamic verification.
            Write-Output ("PLATFORMIO_VERIFY_STATIC_GATE_PASS=" + $(if ($exitCode -eq 0) { 'True' } else { 'False' }))
            Write-Output ("VERIFY_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'test' {
            Assert-NoTrackedSecrets
            Assert-NoHardcodedPort
            $testDir = Join-Path $FirmwareRoot 'test'
            if (-not (Test-Path $testDir)) {
                Write-Output 'TEST_RESULT=SKIP_NO_TESTS'
                Write-Output "PLATFORMIO_TEST_BUILD_PASS=False"
                Write-Output "PLATFORMIO_HARDWARE_TEST_EXECUTION=NOT_RUN"
                break
            }
            Assert-Pio
            $result = Invoke-Pio -PioArgs @('test', '-e', 'nodemcuv2', '--without-uploading', '--without-testing', '--project-dir', $FirmwareRoot) -LogName 'pio_test'
            Write-Output ("PIO_LOG=" + $result.LogPath)
            $exitCode = [int]$result.ExitCode
            # --without-uploading --without-testing means the test *firmware* is
            # compiled and linked; the test cases are NOT executed on any device.
            Write-Output ("PLATFORMIO_TEST_BUILD_PASS=" + $(if ($exitCode -eq 0) { 'True' } else { 'False' }))
            Write-Output "PLATFORMIO_HARDWARE_TEST_EXECUTION=NOT_RUN"
            Write-Output ("TEST_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'build'       { Invoke-Build;        $exitCode = $script:LastRc }
        'clean-build' { Invoke-Build -Clean; $exitCode = $script:LastRc }

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
            $result = Invoke-Pio -PioArgs @('run', '-e', 'nodemcuv2', '-t', 'upload', '--upload-port', $com, '--project-dir', $FirmwareRoot) -LogName 'pio_upload'
            Write-Output ("PIO_LOG=" + $result.LogPath)
            $exitCode = [int]$result.ExitCode
            Write-Output ("UPLOAD_RESULT=" + $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' }))
        }

        'monitor' {
            $com = Resolve-SerialPort
            if (-not $com) {
                Write-Output 'MONITOR_BLOCKED=NO_SERIAL_PORT'
                $exitCode = 7
                break
            }
            $result = Invoke-Pio -PioArgs @('device', 'monitor', '--port', $com, '--baud', '115200') -LogName 'pio_monitor'
            Write-Output ("PIO_LOG=" + $result.LogPath)
            $exitCode = [int]$result.ExitCode
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
            Write-Output 'Profiles (public repository only - none of them compile in credentials):'
            Write-Output '  public                  Default. Cloud transport on, credentials off, live campus'
            Write-Output '                          auth off, IR emission disabled.'
            Write-Output '  local-campus-example    Campus auth compiled against the public Xidian example'
            Write-Output '                          profile (profiles/xidian.example.h). Cloud off, live auth'
            Write-Output '                          off, IR emission disabled. Compile-only demonstration.'
            Write-Output '  public-cloud-example    Same as public, kept as an explicit name for the cloud'
            Write-Output '                          transport matrix entry.'
            Write-Output '  local-wifi              Home/lab WPA/WPA2 with compiled-in credentials'
            Write-Output '                          (wifi_secrets.h) and unattended connect. Cloud off.'
            Write-Output '  local-wifi-cloud        local-wifi + cloud transport.'
            Write-Output ''
            Write-Output 'All profiles keep ENABLE_CONTROLLED_LIVE_AUTH=0 and ENABLE_IR_MUTATING_COMMANDS=0.'
            Write-Output 'Real credentials belong in an untracked campus_secrets.h / wifi_secrets.h, never in this repository.'
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
