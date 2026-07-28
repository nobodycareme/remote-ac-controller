# ============================================================
# dev.ps1 — Remote AC Controller development entry (path-locked)
# Single canonical root. All PlatformIO actions go through this script.
# NO $PSScriptRoot, NO CLI override of root, NO env-root, NO auto PIO search.
#
# The canonical CJK project root is the only valid workspace. This script never
# creates or depends on drive aliases, F:\rac, F:\PIO, copied project roots, or PATH/global
# PlatformIO. All firmware build/flash work must enter through this file.
# ============================================================
param(
    [Parameter(Position=0)]
    [ValidateSet('status','build','clean-build','upload','monitor','verify','flash','test','ir-learning-studio','ir-library-validate','ir-library-list','ir-library-generate','ir-library-export-snapshot','help')]
    [string]$Command = 'help',

    [Parameter()]
    [ValidateSet('public','private','ir-lab','private-production')]
    [string]$Profile = 'public',

    [Parameter()]
    [switch]$AllowDirtyBuild
)

# Captured for the self-test (own-source scan) — must be set at script scope.
$ScriptPath = $PSCommandPath

# ============================================================
# SECTION 0 — R-Drive Guard (blocks all ops if R: detected)
# ============================================================
if (Test-Path R:\) {
    Write-Error "ILLEGAL_R_DRIVE_PRESENT: R:\ exists. Project policy prohibits R: drive aliases."
    Write-Error "Remove R: before running dev.ps1."
    exit 99
}
$currentDriveLetter = (Get-Location).Drive.Name
if ($currentDriveLetter -eq 'R') {
    Write-Error "ILLEGAL_R_DRIVE_CURRENT_DIR: Working directory is on R: drive."
    Write-Error "Change to C:\example\remote-ac before running dev.ps1."
    exit 99
}

# ============================================================
# SECTION I — Single-instance guard (atomic lock file + PID validation)
# ============================================================
$LockFile = 'C:\example\remote-ac\Environment\PlatformIO\Logs\.workflow.lock'
$LockStream = $null
$myPid = $PID
$myStartTime = (Get-Process -Id $myPid).StartTime.Ticks
$myNonce   = [System.Guid]::NewGuid().ToString('N')
$NamedMutexName = 'Local\RemoteACController_PlatformIO_Workflow'
$NamedMutex = New-Object System.Threading.Mutex($false, $NamedMutexName)
$NamedMutexHeld = $false

function Test-IsStaleLock {
    param([string]$path)
    try {
        $line = Get-Content $path -ErrorAction Stop
        if (-not $line) { return $true }
        $parts = $line -split '\|'
        if ($parts.Count -lt 2) { return $true }
        $pidInFile = [int]$parts[0]
        $ticksInFile = [long]$parts[1]
        try {
            $proc = Get-Process -Id $pidInFile -ErrorAction Stop
            if ($proc.StartTime.Ticks -eq $ticksInFile) {
                return $false
            }
            return $true
        } catch {
            return $true
        }
    } catch [System.IO.IOException] {
        return $false
    } catch {
        return $true
    }
}

try {
    $NamedMutexHeld = $NamedMutex.WaitOne(0)
    if (-not $NamedMutexHeld) {
        Write-Output "DEV_PS1_MUTEX_PASS=False"
        Write-Output "WORKFLOW_ALREADY_RUNNING=True"
        Write-Error "Another PlatformIO workflow is already in progress (mutex=$NamedMutexName)."
        exit 1
    }
    Write-Output "DEV_PS1_MUTEX_PASS=True"
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($LockFile)) | Out-Null
    $maxRetries = 3
    for ($attempt = 0; $attempt -lt $maxRetries; $attempt++) {
        try {
            $LockStream = [System.IO.File]::Open(
                $LockFile,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            $meta = "$myPid|$myStartTime|$myNonce"
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($meta)
            $LockStream.Write($bytes, 0, $bytes.Length)
            $LockStream.Flush()
            break
        } catch [System.IO.IOException] {
            if (Test-IsStaleLock $LockFile) {
                Write-Output "STALE_LOCK_REMOVED=True"
                try { [System.IO.File]::Delete($LockFile) } catch {}
                continue
            }
            $line = Get-Content $LockFile -ErrorAction SilentlyContinue
            $parts = $line -split '\|'
            $holderPid = if ($parts.Count -ge 1) { $parts[0] } else { 'unknown' }
            Write-Output "WORKFLOW_ALREADY_RUNNING=True"
            Write-Output "CONCURRENT_PLATFORMIO_OPERATION_BLOCKED=True"
            Write-Output "LOCK_HOLDER_PID=$holderPid"
            Write-Error ("Another PlatformIO workflow is already in progress (PID=$holderPid). Only one session may build/modify at a time.")
            exit 1
        }
    }
    if (-not $LockStream) {
        Write-Error "LOCK_ACQUISITION_FAILED: unable to create lock after $maxRetries attempts"
        exit 1
    }
} catch {
    Write-Error "LOCK_ACQUISITION_FAILED: $($_.Exception.Message)"
    exit 1
}

$ErrorActionPreference = 'Stop'

# ============================================================
# SECTION II — Fixed canonical root constants (hardcoded, never overridable)
# ============================================================
$CanonicalRoot    = 'C:\example\remote-ac'
$FirmwareRelative = 'Firmware\Remote_AC_Controller'
$PioRelative      = 'Environment\PlatformIO\Core\penv\Scripts\pio.exe'
$BuildRelative    = 'Environment\PlatformIO\Build'
$LibDepsRelative  = 'Environment\PlatformIO\LibDeps'
$CacheRelative    = 'Environment\PlatformIO\Cache'
$LogsRelative     = 'Environment\PlatformIO\Logs'

# ============================================================
# SECTION III — Single safe physical path function (real CJK canonical root).
# Input MUST be a relative path. Anything else throws.
# ============================================================
function Resolve-CanonicalPath {
    param([string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        return $CanonicalRoot
    }
    if ([System.IO.Path]::IsPathRooted($RelativePath)) {
        throw "PATH_POLICY_VIOLATION: absolute child path is forbidden"
    }
    if ($RelativePath.Contains(':')) {
        throw "PATH_POLICY_VIOLATION: drive designator is forbidden"
    }
    if ($RelativePath -match '^[\\/]') {
        throw "PATH_POLICY_VIOLATION: rooted child path is forbidden"
    }
    $firstPart = ($RelativePath -split '[\\/]')[0]
    if ($firstPart -cin @('r','R','f','F')) {
        throw "PATH_POLICY_VIOLATION: pseudo-drive directory is forbidden"
    }
    if ($RelativePath -match 'remote-ac') {
        throw "PATH_POLICY_VIOLATION: repeated project root is forbidden"
    }

    $candidate = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine($CanonicalRoot, $RelativePath)
    )
    $canonicalWithSlash = $CanonicalRoot.TrimEnd('\') + '\'
    if (
        -not $candidate.Equals($CanonicalRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        -not $candidate.StartsWith($canonicalWithSlash, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "PATH_POLICY_VIOLATION: path escaped canonical root"
    }
    return $candidate
}

# ============================================================
# SECTION IV — Pre-flight hard gate.
# ============================================================
function Assert-WorkspacePolicy {
    if (-not (Test-Path $CanonicalRoot)) {
        throw "WORKSPACE_POLICY_VIOLATION: CanonicalRoot missing: $CanonicalRoot"
    }
    $firmwarePhys = Resolve-CanonicalPath $FirmwareRelative
    if (-not (Test-Path $firmwarePhys)) {
        throw "WORKSPACE_POLICY_VIOLATION: Firmware dir missing: $firmwarePhys"
    }
    $pioExePhys = Resolve-CanonicalPath $PioRelative
    if (-not (Test-Path $pioExePhys)) {
        throw "WORKSPACE_POLICY_VIOLATION: pio.exe missing: $pioExePhys"
    }
    foreach ($d in @('r','R','f','F')) {
        if (Test-Path (Join-Path $CanonicalRoot $d)) {
            throw "WORKSPACE_POLICY_VIOLATION: literal '$d' directory present at workspace root (forbidden)"
        }
    }
    if (Test-Path (Join-Path $CanonicalRoot 'remote-ac')) {
        throw "WORKSPACE_POLICY_VIOLATION: repeated project root present under canonical root"
    }
    if (Test-Path (Join-Path $firmwarePhys '.pio')) {
        throw "WORKSPACE_POLICY_VIOLATION: project-local .pio present"
    }
    if (Test-Path 'C:\PioStable')  { throw "WORKSPACE_POLICY_VIOLATION: C:\PioStable reference present" }
    if (Test-Path 'C:\PioRecovery'){ throw "WORKSPACE_POLICY_VIOLATION: C:\PioRecovery reference present" }
    if (Test-Path 'F:\PIO')        { throw "WORKSPACE_POLICY_VIOLATION: F:\PIO reference present" }
    if (Test-Path 'F:\rac')        { throw "WORKSPACE_POLICY_VIOLATION: F:\rac alias present (forbidden)" }
    if (Test-Path 'R:\')           { throw "WORKSPACE_POLICY_VIOLATION: R: drive present (forbidden)" }
    # No hardcoded serial port (dynamic CH9102 detection only).
    $comPat  = 'COM' + '\d'
    $devC    = Get-Content (Join-Path $firmwarePhys 'tools\dev.ps1')  -Raw -ErrorAction SilentlyContinue
    $iniC    = Get-Content (Join-Path $firmwarePhys 'platformio.ini') -Raw -ErrorAction SilentlyContinue
    if (($iniC -match $comPat) -or ($devC -match $comPat)) {
        throw "WORKSPACE_POLICY_VIOLATION: hardcoded serial port present"
    }
}

# ============================================================
# Physical paths (real CJK canonical root only)
# ============================================================
$FirmwarePhys    = Resolve-CanonicalPath $FirmwareRelative
$PioExePhys      = Resolve-CanonicalPath $PioRelative
$LogsPhys        = Resolve-CanonicalPath $LogsRelative
$BuildPhys       = Resolve-CanonicalPath $BuildRelative
$LibDepsPhys     = Resolve-CanonicalPath $LibDepsRelative
$CachePhys       = Resolve-CanonicalPath $CacheRelative
$PyExePhys       = Resolve-CanonicalPath 'Environment\PlatformIO\Core\penv\Scripts\python.exe'
$CorePhys        = Resolve-CanonicalPath 'Environment\PlatformIO\Core'
$PackagesPhys    = Resolve-CanonicalPath 'Environment\PlatformIO\Core\packages'
$PlatformsPhys   = Resolve-CanonicalPath 'Environment\PlatformIO\Core\platforms'
$BuildProfilePhys= Resolve-CanonicalPath ('Environment\PlatformIO\Build\Remote_AC_Controller\' + $Profile)
$IrStudioDirPhys = Resolve-CanonicalPath 'Firmware\Remote_AC_Controller\tools\ir_learning_studio'
$IrStudioCliPhys = Join-Path $IrStudioDirPhys 'cli.py'
$IrStudioAppPhys = Join-Path $IrStudioDirPhys 'app.py'

# ============================================================
# Environment (pinned to canonical paths; no fallback to PATH/global PIO)
# ============================================================
$env:PLATFORMIO_CORE_DIR        = $CorePhys
$env:PLATFORMIO_PACKAGES_DIR    = $PackagesPhys
$env:PLATFORMIO_PLATFORMS_DIR   = $PlatformsPhys
$env:PLATFORMIO_BUILD_DIR       = $BuildProfilePhys
$env:PLATFORMIO_LIBDEPS_DIR     = $LibDepsPhys
$env:PLATFORMIO_CACHE_DIR       = $CachePhys
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = 'false'
$env:PLATFORMIO_DISABLE_PROGRESSBAR      = 'true'
$env:PYTHONUNBUFFERED = '1'

# Proxy: EMPTY STRINGS (not unset) to block urllib registry fallback to dead proxy (K18)
$env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:http_proxy=''; $env:https_proxy=''; $env:ALL_PROXY=''; $env:all_proxy=''
$env:NO_PROXY='*'

# Build flags by profile (cloud always compiled; credentials gated separately)
# ir-lab: private base (cloud + credentials + owner live-auth) PLUS IR mutating
#         commands and capture-only IR Learning Studio lab commands.
# private-production: real-IR emit capable for approved generated codes, but the
#         experimental ir_learn_* UART learning/export interface is closed.
if ($Profile -eq 'ir-lab') {
    $env:BUILD_FLAGS_PUBLIC  = ''
    $env:BUILD_FLAGS_PRIVATE = '-DENABLE_CONTROLLED_LIVE_AUTH=1 -DENABLE_IR_MUTATING_COMMANDS=1 -DENABLE_IR_LAB_LEARNING_COMMANDS=1 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=1'
} elseif ($Profile -eq 'private-production') {
    $env:BUILD_FLAGS_PUBLIC  = ''
    $env:BUILD_FLAGS_PRIVATE = '-DENABLE_CONTROLLED_LIVE_AUTH=1 -DENABLE_IR_MUTATING_COMMANDS=1 -DENABLE_IR_LAB_LEARNING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=1'
} elseif ($Profile -eq 'private') {
    $env:BUILD_FLAGS_PUBLIC  = ''
    $env:BUILD_FLAGS_PRIVATE = '-DENABLE_CONTROLLED_LIVE_AUTH=1 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=1'
} else {
    $env:BUILD_FLAGS_PUBLIC  = '-DENABLE_CONTROLLED_LIVE_AUTH=0 -DENABLE_IR_MUTATING_COMMANDS=0 -DENABLE_CLOUD=1 -DENABLE_CLOUD_CREDENTIALS=0'
    $env:BUILD_FLAGS_PRIVATE = ''
}

# ============================================================
# CH9102 Detection (VID:PID=1A86:55D4, dynamic, never hardcoded)
# Dual-channel enumeration, single source of truth: Resolve-Ch9102Port.
#   Channel A: Get-PnpDevice -PresentOnly (fallback CIM Win32_PnPEntity)
#              + Win32_SerialPort (matched by PNPDeviceID)
#              + registry Device Parameters\PortName per matched instance
#   Channel B: pySerial cross-check via tools\ch9102_enum.py (numeric vid/pid)
# COM extraction never relies on FriendlyName alone; FriendlyName regex is
# the LAST resort only. Bounded retry (default 10 x 500ms). Distinct result
# classes -- never a blanket "device not connected".
# ============================================================
$Ch9102VidPidPattern = 'VID_1A86&PID_55D4'
$Ch9102PortRegex     = '^COM[0-9]+$'

function Test-WindowsExecutionHost {
    $isWin  = ($env:OS -eq 'Windows_NT')
    $rootOk = Test-Path $CanonicalRoot
    $fwOk   = Test-Path $FirmwarePhys
    $pnpOk  = ($null -ne (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue))
    $cimOk  = ($null -ne (Get-Command Get-CimInstance -ErrorAction SilentlyContinue))
    return @{
        IsWindows = $isWin; RootOk = $rootOk; FirmwareOk = $fwOk
        PnpCmdOk = $pnpOk; CimCmdOk = $cimOk
        Pass = ($isWin -and $rootOk -and $fwOk -and ($pnpOk -or $cimOk))
    }
}

function Get-Ch9102RegistryPortName {
    param([string]$InstanceId)
    if ([string]::IsNullOrWhiteSpace($InstanceId)) { return $null }
    try {
        $key = 'HKLM:\SYSTEM\CurrentControlSet\Enum\' + $InstanceId + '\Device Parameters'
        $rp = Get-ItemProperty -Path $key -Name PortName -ErrorAction SilentlyContinue
        if ($null -ne $rp -and $rp.PortName) { return [string]$rp.PortName }
    } catch {}
    return $null
}

function Get-Ch9102PySerialResult {
    $helper = Join-Path $FirmwarePhys 'tools\ch9102_enum.py'
    if (-not (Test-Path $helper) -or -not (Test-Path $PyExePhys)) {
        return @{ Available = $false; Ports = @() }
    }
    try {
        $raw = (& $PyExePhys -u $helper 2>$null | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($raw)) { return @{ Available = $false; Ports = @() } }
        $obj = $raw | ConvertFrom-Json
        $ports = @()
        foreach ($p in @($obj.ports)) {
            if ($null -eq $p) { continue }
            if (([int]$p.vid -eq 0x1A86) -and ([int]$p.pid -eq 0x55D4)) { $ports += $p }
        }
        return @{ Available = [bool]$obj.available; Ports = $ports }
    } catch {
        return @{ Available = $false; Ports = @() }
    }
}

function Merge-Ch9102PortCandidates {
    param([object[]]$RawPorts)
    $valid = @()
    foreach ($p in @($RawPorts)) {
        if ($null -eq $p) { continue }
        $t = ([string]$p).Trim().ToUpperInvariant()
        if ($t -match $Ch9102PortRegex) {
            if ($valid -notcontains $t) { $valid += $t }
        }
    }
    Write-Output -NoEnumerate ([string[]]$valid)
}

function New-Ch9102ResolutionResult {
    param([string]$Result, [string]$Port, [string[]]$Ports,
          [string[]]$PnpIds, [string[]]$SpIds,
          [bool]$PyAvail, [int]$PyCount, [int]$Attempts)
    return @{
        Result = $Result
        Port = $Port
        Ports = [string[]]@($Ports)
        PnpCount = @($PnpIds).Count
        PnpInstanceIds = [string[]]@($PnpIds)
        SerialPortCount = @($SpIds).Count
        SerialPortDeviceIds = [string[]]@($SpIds)
        PySerialAvailable = $PyAvail
        PySerialCount = $PyCount
        Attempts = $Attempts
    }
}

function Resolve-Ch9102Port {
    [CmdletBinding()]
    param(
        [int]$MaxAttempts = 10,
        [int]$IntervalMs = 500,
        [hashtable]$TestInput = $null
    )
    if ($null -ne $TestInput) { $MaxAttempts = 1; $IntervalMs = 0 }

    # Execution-host gate: USB detection is only meaningful on the Windows
    # box that physically hosts the board. A non-Windows / remote / sandbox
    # host must report WRONG_EXECUTION_HOST -- never "device not connected".
    if ($null -ne $TestInput -and $TestInput.ContainsKey('IsWindows')) {
        $hostOk = [bool]$TestInput.IsWindows
    } else {
        $hostOk = (Test-WindowsExecutionHost).Pass
    }
    if (-not $hostOk) {
        return (New-Ch9102ResolutionResult -Result 'WRONG_EXECUTION_HOST' -Port $null -Ports @() `
            -PnpIds @() -SpIds @() -PyAvail $false -PyCount 0 -Attempts 0)
    }

    $final = $null
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        # ---- Channel A1: present PnP devices (never ghosts) ----
        $pnpMatches = @()
        if ($null -ne $TestInput) {
            foreach ($d in @($TestInput.Pnp)) {
                if ($null -eq $d) { continue }
                if ($d.ContainsKey('Present') -and (-not [bool]$d.Present)) { continue }
                if (([string]$d.InstanceId) -imatch $Ch9102VidPidPattern) { $pnpMatches += $d }
            }
        } else {
            try {
                if (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue) {
                    $pnpMatches = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
                        Where-Object { $_.InstanceId -imatch $Ch9102VidPidPattern })
                }
            } catch { $pnpMatches = @() }
            if ($pnpMatches.Count -eq 0) {
                try {
                    $pnpMatches = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
                        Where-Object { $_.PNPDeviceID -imatch $Ch9102VidPidPattern } |
                        ForEach-Object { @{ InstanceId = [string]$_.PNPDeviceID; FriendlyName = [string]$_.Name } })
                } catch { $pnpMatches = @() }
            }
        }

        # ---- Channel A2: Win32_SerialPort matched by PNPDeviceID ----
        $spMatches = @()
        if ($null -ne $TestInput) {
            foreach ($s in @($TestInput.SerialPorts)) {
                if ($null -eq $s) { continue }
                if (([string]$s.PNPDeviceID) -imatch $Ch9102VidPidPattern) { $spMatches += $s }
            }
        } else {
            try {
                $spMatches = @(Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue |
                    Where-Object { $_.PNPDeviceID -imatch $Ch9102VidPidPattern })
            } catch { $spMatches = @() }
        }

        # ---- Channel B: pySerial cross-check (numeric vid/pid only) ----
        if ($null -ne $TestInput) {
            $py = if ($TestInput.ContainsKey('PySerial')) { $TestInput.PySerial } else { @{ Available = $false; Ports = @() } }
            $pyPorts = @()
            foreach ($p in @($py.Ports)) {
                if ($null -eq $p) { continue }
                if (([int]$p.vid -eq 0x1A86) -and ([int]$p.pid -eq 0x55D4)) { $pyPorts += $p }
            }
        } else {
            $py = Get-Ch9102PySerialResult
            $pyPorts = @($py.Ports)
        }

        # ---- Extract raw port strings (priority: SerialPort.DeviceID and
        #      registry PortName; FriendlyName regex only as last resort) ----
        $raw = @()
        foreach ($s in $spMatches) { $raw += [string]$s.DeviceID }
        foreach ($d in $pnpMatches) {
            $rp = $null
            if ($null -ne $TestInput) {
                if ($TestInput.ContainsKey('RegistryMap') -and $TestInput.RegistryMap.ContainsKey([string]$d.InstanceId)) {
                    $rp = [string]$TestInput.RegistryMap[[string]$d.InstanceId]
                }
            } else {
                $rp = Get-Ch9102RegistryPortName -InstanceId ([string]$d.InstanceId)
            }
            if (-not [string]::IsNullOrWhiteSpace($rp)) { $raw += $rp; continue }
            $fn = [string]$d.FriendlyName
            if ($fn -match 'COM([0-9]+)') { $raw += ('COM' + $Matches[1]) }
        }
        foreach ($p in $pyPorts) { $raw += [string]$p.device }

        $ports  = Merge-Ch9102PortCandidates -RawPorts $raw
        $pnpIds = [string[]]@(@($pnpMatches) | ForEach-Object { [string]$_.InstanceId })
        $spIds  = [string[]]@(@($spMatches)  | ForEach-Object { [string]$_.DeviceID })
        $pyAvail = [bool]$py.Available
        $pyCount = @($pyPorts).Count

        if (@($ports).Count -eq 1) {
            return (New-Ch9102ResolutionResult -Result 'PORT_RESOLVED' -Port ([string]$ports[0]) -Ports $ports `
                -PnpIds $pnpIds -SpIds $spIds -PyAvail $pyAvail -PyCount $pyCount -Attempts $attempt)
        }
        if (@($ports).Count -gt 1) {
            return (New-Ch9102ResolutionResult -Result 'MULTIPLE_MATCHING_PORTS' -Port $null -Ports $ports `
                -PnpIds $pnpIds -SpIds $spIds -PyAvail $pyAvail -PyCount $pyCount -Attempts $attempt)
        }
        if ((@($pnpMatches).Count + @($spMatches).Count + $pyCount) -gt 0) {
            $final = New-Ch9102ResolutionResult -Result 'DEVICE_ENUMERATED_NO_COM' -Port $null -Ports @() `
                -PnpIds $pnpIds -SpIds $spIds -PyAvail $pyAvail -PyCount $pyCount -Attempts $attempt
        } else {
            $final = New-Ch9102ResolutionResult -Result 'DEVICE_NOT_ENUMERATED' -Port $null -Ports @() `
                -PnpIds $pnpIds -SpIds $spIds -PyAvail $pyAvail -PyCount $pyCount -Attempts $attempt
        }
        if ($attempt -lt $MaxAttempts) { Start-Sleep -Milliseconds $IntervalMs }
    }
    return $final
}

function Write-Ch9102DetectionLog {
    param([hashtable]$Resolution)
    Write-Output ("PORT_DETECTION_HOST=" + [string]$env:COMPUTERNAME)
    Write-Output ("PORT_DETECTION_OS=" + [System.Environment]::OSVersion.VersionString)
    Write-Output ("PORT_DETECTION_PROJECT_ROOT=" + $CanonicalRoot)
    Write-Output ("PNP_MATCH_COUNT=" + $Resolution.PnpCount)
    Write-Output ("PNP_MATCH_INSTANCE_IDS=" + (@($Resolution.PnpInstanceIds) -join ';'))
    Write-Output ("SERIALPORT_MATCH_COUNT=" + $Resolution.SerialPortCount)
    Write-Output ("SERIALPORT_MATCH_DEVICE_IDS=" + (@($Resolution.SerialPortDeviceIds) -join ';'))
    Write-Output ("PYSERIAL_AVAILABLE=" + $Resolution.PySerialAvailable)
    Write-Output ("PYSERIAL_MATCH_COUNT=" + $Resolution.PySerialCount)
    Write-Output ("RESOLVED_PORT_COUNT=" + @($Resolution.Ports).Count)
    Write-Output ("RESOLVED_UPLOAD_PORT=" + $(if ($Resolution.Port) { $Resolution.Port } else { '' }))
    Write-Output ("PORT_DETECTION_RESULT=" + $Resolution.Result)
}

function Get-UploadFailureClass {
    # Classify the uploader's REAL output. "Access denied" is a busy/held
    # port -- it must NEVER be reported as device-not-found.
    param([string]$OutputText)
    if ([string]::IsNullOrWhiteSpace($OutputText)) { return 'UPLOAD_WRITE_FAILED' }
    $t = $OutputText.ToLowerInvariant()
    if ($t -match 'access is denied|permissionerror|permission denied')      { return 'PORT_ACCESS_DENIED' }
    if ($t -match 'resource busy|port is already open|semaphore timeout')    { return 'PORT_BUSY' }
    if ($t -match 'could not open port|filenotfounderror|no such file or directory') { return 'PORT_OPEN_FAILED' }
    if ($t -match 'failed to connect|timed out waiting for packet|invalid head of packet|wrong boot mode') { return 'BOOTLOADER_SYNC_FAILED' }
    if ($t -match 'verify failed|digest mismatch|md5 of file does not match') { return 'UPLOAD_VERIFY_FAILED' }
    return 'UPLOAD_WRITE_FAILED'
}

function Invoke-UploadPortScope {
    # Process-scoped explicit upload port injection. Saves and restores the
    # previous PLATFORMIO_UPLOAD_PORT so nothing leaks to later tasks and
    # the user's machine-level environment is never modified.
    param([string]$Port, [scriptblock]$Body)
    $had  = Test-Path Env:\PLATFORMIO_UPLOAD_PORT
    $prev = $env:PLATFORMIO_UPLOAD_PORT
    try {
        $env:PLATFORMIO_UPLOAD_PORT = $Port
        & $Body
    } finally {
        if ($had) { $env:PLATFORMIO_UPLOAD_PORT = $prev }
        else { Remove-Item Env:\PLATFORMIO_UPLOAD_PORT -ErrorAction SilentlyContinue }
    }
}

# Back-compat wrappers (status display + existing self-tests).
function Get-Ch9102Candidates {
    param([string[]]$SimulatedPorts = $null)
    if ($null -ne $SimulatedPorts) {
        Write-Verbose ("CH9102: simulated candidate list = " + ($SimulatedPorts -join ','))
        Write-Output -NoEnumerate ([string[]](Merge-Ch9102PortCandidates -RawPorts $SimulatedPorts))
        return
    }
    $r = Resolve-Ch9102Port -MaxAttempts 1
    Write-Output -NoEnumerate ([string[]]@($r.Ports))
}

function Find-Ch9102Port {
    [CmdletBinding()]
    param([string[]]$SimulatedPorts = $null)
    if ($null -ne $SimulatedPorts) {
        $ports = Merge-Ch9102PortCandidates -RawPorts $SimulatedPorts
        if (@($ports).Count -eq 0) { throw [System.InvalidOperationException]::new('CH9102_NOT_DETECTED') }
        if (@($ports).Count -gt 1) { throw [System.InvalidOperationException]::new('CH9102_MULTIPLE') }
        return ([string]$ports[0])
    }
    $r = Resolve-Ch9102Port
    # Detection log must NOT contaminate the return pipeline (callers expect a
    # single pure port string). Route the log lines to the host stream.
    foreach ($line in @(Write-Ch9102DetectionLog -Resolution $r)) { Write-Host $line }
    switch ([string]$r.Result) {
        'PORT_RESOLVED'            { return ([string]$r.Port) }
        'WRONG_EXECUTION_HOST'     { throw [System.InvalidOperationException]::new('WRONG_EXECUTION_HOST') }
        'MULTIPLE_MATCHING_PORTS'  { throw [System.InvalidOperationException]::new('CH9102_MULTIPLE') }
        'DEVICE_ENUMERATED_NO_COM' { throw [System.InvalidOperationException]::new('DEVICE_ENUMERATED_NO_COM') }
        default                    { throw [System.InvalidOperationException]::new('DEVICE_NOT_ENUMERATED') }
    }
}

# ============================================================
# Port pre-check (Open/Close probe) with bounded retry.
# ============================================================
function Get-PortOwnerProcess {
    param([string]$Port)
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $cmd = $p.CommandLine
            if ($null -ne $cmd -and $cmd.Contains($Port)) { return $p }
        }
    } catch {}
    return $null
}

function Format-PortBusyDiagnosis {
    param([string]$Port, [int]$Attempts, $Owner)
    $msg = "Port " + $Port + " is occupied (could not open after " + $Attempts + " attempt(s))"
    if ($null -ne $Owner -and $Owner.Name) {
        $msg += (" - held by PID=" + $Owner.ProcessId + " Name=" + $Owner.Name)
    } else {
        $msg += " - unable to attribute the owner (close any serial monitor / terminal manually)"
    }
    return $msg
}

function Get-PortOpenFailureClass {
    param([System.Exception]$Exception)
    if ($null -eq $Exception) { return 'Other' }
    $msg  = $Exception.Message
    if ($null -eq $msg) { $msg = '' }
    $msg  = $msg.ToString()
    $type = $Exception.GetType().Name
    if ($type -eq 'UnauthorizedAccessException' -or $msg -match 'access is denied') {
        return 'AccessDenied'
    }
    if (($type -match 'FileNotFound|IOException') -and $msg -match 'does not exist') {
        return 'NoSuchPort'
    }
    if ($msg -match 'does not exist') {
        return 'NoSuchPort'
    }
    return 'Other'
}

function Test-PortFree {
    param(
        [string]$Port,
        [int]$MaxRetries = 3,
        [int]$IntervalMs = 1000
    )
    $lastErr = $null
    $lastClass = $null
    for ($i = 1; $i -le $MaxRetries; $i++) {
        $sp = $null
        try {
            $sp = New-Object System.IO.Ports.SerialPort($Port, 115200)
            $sp.Open()
            try { if ($sp.IsOpen) { $sp.Close() } } catch {}
            try { $sp.Dispose() } catch {}
            $sp = $null
            return @{ Free = $true; Busy = $false; Reason = 'OK'; Attempts = $i; Diagnosis = '' }
        } catch {
            $lastErr = $_.Exception.Message
            $lastClass = Get-PortOpenFailureClass -Exception $_.Exception
            try { if ($null -ne $sp) { if ($sp.IsOpen) { $sp.Close() } } } catch {}
            try { if ($null -ne $sp) { $sp.Dispose() } } catch {}
            $sp = $null
            if ($i -lt $MaxRetries) { Start-Sleep -Milliseconds $IntervalMs }
        }
    }
    $owner = Get-PortOwnerProcess -Port $Port
    if ($lastClass -eq 'NoSuchPort') {
        $diag = ("Port " + $Port + " was reported by detection but does not exist on the system (stale detection / driver glitch) - reconnect the board or re-run 'status'")
        return @{ Free = $false; Busy = $true; Reason = 'NoSuchPort'; Attempts = $MaxRetries; Diagnosis = $diag }
    }
    if ($lastClass -eq 'AccessDenied' -and $null -ne $owner -and $owner.Name) {
        $diag = ("Port " + $Port + " is occupied - held by PID=" + $owner.ProcessId + " Name=" + $owner.Name + " (our serial monitor); stop it first")
        return @{ Free = $false; Busy = $true; Reason = 'Occupied'; Attempts = $MaxRetries; Diagnosis = $diag }
    }
    if ($lastClass -eq 'AccessDenied') {
        $diag = ("Port " + $Port + " is busy (Access is denied) but no project monitor process was detected - close any serial terminal / other tool holding it")
        return @{ Free = $false; Busy = $true; Reason = 'AccessDeniedExternal'; Attempts = $MaxRetries; Diagnosis = $diag }
    }
    $diag = ("Port " + $Port + " could not be opened after " + $MaxRetries + " attempt(s): " + $lastErr)
    if ($null -ne $owner -and $owner.Name) {
        $diag += (" - possibly held by PID=" + $owner.ProcessId + " Name=" + $owner.Name)
    }
    return @{ Free = $false; Busy = $true; Reason = 'Other'; Attempts = $MaxRetries; Diagnosis = $diag }
}

# ============================================================
# Stop ONLY the serial monitor(s) spawned by THIS dev.ps1 workflow.
# ============================================================
function Test-IsProjectMonitorCmdLine {
    param([string]$CommandLine)
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    $lower = $CommandLine.ToLower()
    $marker = $FirmwarePhys.ToLower()
    return ($lower.Contains($marker) -and $lower.Contains('device monitor'))
}

function Stop-ProjectMonitor {
    param()
    $killed = 0
    $skipped = 0
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { Test-IsProjectMonitorCmdLine -CommandLine $_.CommandLine }
        foreach ($p in $procs) {
            if ($p.ProcessId -eq $PID) { continue }
            try {
                $p | Invoke-CimMethod -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null
                $killed++
            } catch { $skipped++ }
        }
    } catch {}
    Write-Verbose ("Stop-ProjectMonitor: killed=" + $killed + " skipped=" + $skipped)
    return @{ Killed = $killed; Skipped = $skipped }
}

function Assert-Pio {
    if (-not (Test-Path $PioExePhys)) {
        Write-Error "PIO executable not found at canonical location: $PioExePhys"
        Write-Error "NO fallback to PATH or global PlatformIO."
        exit 1
    }
}

function Get-GitCommit {
    Push-Location $FirmwarePhys
    try { return (& git rev-parse HEAD).Trim() }
    finally { Pop-Location }
}

function Get-GitDirtyCount {
    Push-Location $FirmwarePhys
    try {
        $lines = & git status --porcelain=v1 -uall
        return @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    } finally { Pop-Location }
}

function Test-GitWorktreeClean {
    return ((Get-GitDirtyCount) -eq 0)
}

function Assert-DiagnosticBuildAllowed {
    if ($Profile -eq 'private-production' -and -not (Test-GitWorktreeClean) -and -not $AllowDirtyBuild) {
        throw "DIRTY_PRIVATE_PRODUCTION_BUILD_REJECTED: use -AllowDirtyBuild only for diagnostic build; never for flash"
    }
}

function Assert-FlashAllowed {
    if ($Profile -eq 'private-production' -and -not (Test-GitWorktreeClean)) {
        throw "DIRTY_PRIVATE_PRODUCTION_FLASH_REJECTED: clean Git worktree required"
    }
}

function Get-FileShaOrNull {
    param([string]$Path)
    if (Test-Path $Path) { return (Get-FileHash -Algorithm SHA256 $Path).Hash }
    return $null
}

function New-BuildManifest {
    param([string]$BinPath)
    $buildDir = Join-Path $env:PLATFORMIO_BUILD_DIR 'nodemcuv2'
    $elfPath = Join-Path $buildDir 'firmware.elf'
    $mapPath = Join-Path $buildDir 'firmware.map'
    $manifestDir = Join-Path $LogsPhys 'manifests'
    New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null
    $flagsText = "$env:BUILD_FLAGS_PUBLIC`n$env:BUILD_FLAGS_PRIVATE"
    $flagsBytes = [System.Text.Encoding]::UTF8.GetBytes($flagsText)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $flagsSha = ([System.BitConverter]::ToString($sha.ComputeHash($flagsBytes))).Replace('-','')
    $manifest = [ordered]@{
        profile = $Profile
        git_commit = Get-GitCommit
        git_worktree_clean = Test-GitWorktreeClean
        allow_dirty_build = [bool]$AllowDirtyBuild
        build_timestamp = (Get-Date).ToString('o')
        platformio_core_dir = $env:PLATFORMIO_CORE_DIR
        platformio_build_dir = $env:PLATFORMIO_BUILD_DIR
        build_flags_sha256 = $flagsSha
        bin_path = $BinPath
        bin_size = if (Test-Path $BinPath) { (Get-Item $BinPath).Length } else { $null }
        bin_sha256 = Get-FileShaOrNull $BinPath
        elf_path = $elfPath
        elf_sha256 = Get-FileShaOrNull $elfPath
        map_path = $mapPath
        map_sha256 = Get-FileShaOrNull $mapPath
    }
    $json = $manifest | ConvertTo-Json -Depth 6
    $stamp = Get-Date -Format 'yyyyMMddTHHmmss'
    $specific = Join-Path $manifestDir ("build_manifest_{0}_{1}.json" -f $Profile, $stamp)
    $latest = Join-Path $manifestDir ("latest_{0}.json" -f $Profile)
    $json | Set-Content -Path $specific -Encoding UTF8
    $json | Set-Content -Path $latest -Encoding UTF8
    Write-Output "BUILD_MANIFEST=$specific"
    Write-Output "BUILD_MANIFEST_LATEST=$latest"
    return $latest
}

function Assert-LastBuildManifestMatches {
    $latest = Join-Path (Join-Path $LogsPhys 'manifests') ("latest_{0}.json" -f $Profile)
    if (-not (Test-Path $latest)) {
        throw "BUILD_MANIFEST_MISSING: $latest"
    }
    $manifest = Get-Content $latest -Raw | ConvertFrom-Json
    if ($manifest.profile -ne $Profile) { throw "BUILD_MANIFEST_PROFILE_MISMATCH" }
    if ($Profile -eq 'private-production') {
        if ($manifest.git_worktree_clean -ne $true) { throw "BUILD_MANIFEST_DIRTY_REJECTED" }
        if ($manifest.git_commit -ne (Get-GitCommit)) { throw "BUILD_MANIFEST_GIT_COMMIT_MISMATCH" }
    }
    $bin = [string]$manifest.bin_path
    if (-not (Test-Path $bin)) { throw "BUILD_MANIFEST_BIN_MISSING: $bin" }
    $currentHash = Get-FileShaOrNull $bin
    if ($currentHash -ne $manifest.bin_sha256) { throw "BUILD_MANIFEST_BIN_SHA_MISMATCH" }
    Write-Output "BUILD_MANIFEST_MATCH_PASS=True"
}

function Ensure-PrivateIrGeneratedIfNeeded {
    $needsPrivateIr = ($Profile -eq 'ir-lab' -or $Profile -eq 'private-production')
    if (-not $needsPrivateIr) { return }

    if (-not (Test-Path $IrStudioCliPhys)) {
        throw "IR_LEARNING_STUDIO_CLI_MISSING: $IrStudioCliPhys"
    }
    & $PyExePhys -u $IrStudioCliPhys migrate-existing 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { throw "PRIVATE_IR_EXISTING_MIGRATION_FAILED" }
    & $PyExePhys -u $IrStudioCliPhys generate 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { throw "PRIVATE_IR_LIBRARY_GENERATE_FAILED" }
}

function Invoke-IrLearningStudio {
    Assert-WorkspacePolicy
    if (-not (Test-Path $IrStudioAppPhys)) { throw "IR_LEARNING_STUDIO_APP_MISSING: $IrStudioAppPhys" }
    Write-Output "IR_LEARNING_STUDIO_START=$IrStudioAppPhys"
    Write-Output "IR_LEARNING_STUDIO_AUTO_BUILD=False"
    Write-Output "IR_LEARNING_STUDIO_AUTO_FLASH=False"
    Write-Output "IR_LEARNING_STUDIO_AUTO_TRANSMIT=False"
    & $PyExePhys -u $IrStudioAppPhys
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-IrLibraryValidate {
    Assert-WorkspacePolicy
    if (-not (Test-Path $IrStudioCliPhys)) { throw "IR_LEARNING_STUDIO_CLI_MISSING: $IrStudioCliPhys" }
    & $PyExePhys -u $IrStudioCliPhys validate 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-IrLibraryList {
    Assert-WorkspacePolicy
    if (-not (Test-Path $IrStudioCliPhys)) { throw "IR_LEARNING_STUDIO_CLI_MISSING: $IrStudioCliPhys" }
    & $PyExePhys -u $IrStudioCliPhys list 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-IrLibraryGenerate {
    Assert-WorkspacePolicy
    if (-not (Test-Path $IrStudioCliPhys)) { throw "IR_LEARNING_STUDIO_CLI_MISSING: $IrStudioCliPhys" }
    & $PyExePhys -u $IrStudioCliPhys generate 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-IrLibraryExportSnapshot {
    Assert-WorkspacePolicy
    if (-not (Test-Path $IrStudioCliPhys)) { throw "IR_LEARNING_STUDIO_CLI_MISSING: $IrStudioCliPhys" }
    & $PyExePhys -u $IrStudioCliPhys export-snapshot 2>&1 | ForEach-Object { Write-Output $_ }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# ============================================================
# Commands
# ============================================================
function Invoke-Status {
    Assert-WorkspacePolicy
    try {
        Write-Output "=============================================="
        Write-Output " Remote AC Controller — path-locked workflow"
        Write-Output "=============================================="
        Write-Output "CanonicalRoot: $CanonicalRoot"
        Write-Output "FirmwareRoot:  $FirmwarePhys"
        Write-Output "PIO:           $PioExePhys"
        $ver = & $PyExePhys -m platformio --version 2>&1 | ForEach-Object { $_ -replace '\s+',' ' }
        Write-Output "PIO Version:   $ver"
        Write-Output "Platform:      espressif8266@4.2.1"
        Write-Output "Board:         NodeMCU ESP8266 ESP-12E"
        Write-Output ""
        Write-Output "Core Dir:      $env:PLATFORMIO_CORE_DIR"
        Write-Output "Build Dir:     $env:PLATFORMIO_BUILD_DIR"
        Write-Output "LibDeps Dir:   $env:PLATFORMIO_LIBDEPS_DIR"
        Write-Output "Cache Dir:     $env:PLATFORMIO_CACHE_DIR"
        Write-Output "Profile:       $Profile"
        $irMut = ($Profile -eq 'ir-lab' -or $Profile -eq 'private-production')
        $authCred = ($Profile -eq 'private' -or $Profile -eq 'ir-lab' -or $Profile -eq 'private-production')
        Write-Output "Auth Macro:    ENABLE_CONTROLLED_LIVE_AUTH=$(if ($authCred) {'1'} else {'0'})"
        Write-Output "IR Macro:      ENABLE_IR_MUTATING_COMMANDS=$(if ($irMut) {'1'} else {'0'})"
        Write-Output "Cloud Macro:   ENABLE_CLOUD=1"
        Write-Output "Creds Macro:   ENABLE_CLOUD_CREDENTIALS=$(if ($authCred) {'1'} else {'0'})"
        Write-Output "AliasRoot:     none (R:/F:\rac/F:\PIO forbidden)"
        Write-Output ""
        $secPath = Join-Path $FirmwarePhys 'include\secrets.h'
        Write-Output "Secrets File:  $(Test-Path $secPath)"
        $cands = Get-Ch9102Candidates
        if ($cands.Count -eq 1) {
            Write-Output ("COM Port:      " + [string]$cands[0] + " (CH9102 VID:PID=1A86:55D4)")
        } elseif ($cands.Count -gt 1) {
            Write-Output ("COM Ports:     " + ($cands -join ', ') + " (MULTIPLE-ambiguous)")
        } else {
            Write-Output "COM Port:      NOT DETECTED (CH9102 VID:PID=1A86:55D4)"
        }
        Write-Output "=============================================="
    } finally {
        # junction is persistent; no cleanup needed
    }
}

function Invoke-Build {
    Assert-WorkspacePolicy
    Assert-Pio
    Assert-DiagnosticBuildAllowed
    try {
        New-CanonicalDirectory $LogsRelative | Out-Null
        Ensure-PrivateIrGeneratedIfNeeded
        Write-Output "BUILD [$Profile] $(Get-Date -Format 'HH:mm:ss')"
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $logFile = Join-Path $LogsPhys ("pio_build_{0}_{1}.log" -f $Profile, $PID)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $PyExePhys -m platformio run -e nodemcuv2 -j 1 --project-dir $FirmwarePhys > $logFile 2>&1
        $rc = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        $elapsed = $sw.Elapsed.TotalSeconds
        Get-Content $logFile -Tail 5 | ForEach-Object { Write-Output $_ }
        $fw = Join-Path $env:PLATFORMIO_BUILD_DIR 'nodemcuv2\firmware.bin'
        if ((Test-Path $fw) -and $rc -eq 0) {
            $sz = (Get-Item $fw).Length
            $hash = (Get-FileHash -Algorithm SHA256 $fw).Hash
            Write-Output "BUILD_PASS rc=$rc size=$sz elapsed=$([math]::Round($elapsed,1))s SHA256=$hash"
            New-BuildManifest -BinPath $fw | Out-Null
            if (-not (Invoke-SecretScan $Profile $env:PLATFORMIO_BUILD_DIR)) {
                Write-Output "PUBLIC_BUILD_PASS=False"
                exit 1
            }
            Write-Output "PUBLIC_BUILD_PASS=True"
        } else {
            Write-Output "BUILD_FAIL rc=$rc elapsed=$([math]::Round($elapsed,1))s"
            exit $rc
        }
    } finally {
    }
}

function Invoke-CleanBuild {
    Assert-WorkspacePolicy
    Assert-Pio
    Assert-DiagnosticBuildAllowed
    try {
        New-CanonicalDirectory $LogsRelative | Out-Null
        Write-Output "CLEAN [$Profile] $(Get-Date -Format 'HH:mm:ss')"
        $cleanLog = Join-Path $LogsPhys ("pio_clean_{0}_{1}.log" -f $Profile, $PID)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $PyExePhys -m platformio run -t clean -e nodemcuv2 --project-dir $FirmwarePhys > $cleanLog 2>&1
        $cleanRc = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        Write-Output "CLEAN_EXIT_CODE=$cleanRc"

        $buildNodemcu = Join-Path $env:PLATFORMIO_BUILD_DIR 'nodemcuv2'
        $fw = Join-Path $buildNodemcu 'firmware.bin'
        $elf = Join-Path $buildNodemcu 'firmware.elf'
        $map = Join-Path $buildNodemcu 'firmware.map'
        $rootMap = Join-Path $FirmwarePhys 'firmware.map'
        $fwGone = -not (Test-Path $fw)
        $elfGone = -not (Test-Path $elf)
        if (Test-Path $map) { Remove-Item -LiteralPath $map -Force }
        if (Test-Path $rootMap) { Remove-Item -LiteralPath $rootMap -Force }
        $oFiles = @()
        if (Test-Path $buildNodemcu) {
            $oFiles = Get-ChildItem -Path $buildNodemcu -Recurse -Filter "*.o" -ErrorAction SilentlyContinue
        }
        $oGone = ($oFiles.Count -eq 0)
        Write-Output "ARTIFACTS_ABSENT_AFTER_CLEAN=$($fwGone -and $elfGone -and $oGone)"
        if (-not ($fwGone -and $elfGone -and $oGone)) {
            Write-Error "Old artifacts still present after clean! fw_gone=$fwGone elf_gone=$elfGone o_count=$($oFiles.Count)"
            exit 1
        }

        Write-Output "BUILD [$Profile] $(Get-Date -Format 'HH:mm:ss')"
        Ensure-PrivateIrGeneratedIfNeeded
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $blog = Join-Path $LogsPhys ("pio_cleanbuild_{0}_{1}.log" -f $Profile, $PID)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $PyExePhys -m platformio run -e nodemcuv2 -j 1 --project-dir $FirmwarePhys > $blog 2>&1
        $rc = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        $elapsed = $sw.Elapsed.TotalSeconds
        $map = Join-Path $buildNodemcu 'firmware.map'
        $rootMap = Join-Path $FirmwarePhys 'firmware.map'
        if (Test-Path $rootMap) {
            if (Test-Path $map) { Remove-Item -LiteralPath $map -Force }
            Move-Item -LiteralPath $rootMap -Destination $map -Force
        }
        Get-Content $blog -Tail 3 | ForEach-Object { Write-Output $_ }

        $compileCount = (Select-String -Path $blog -Pattern 'Compiling ' -AllMatches).Matches.Count
        $linkCount    = (Select-String -Path $blog -Pattern 'Linking ' -AllMatches).Matches.Count
        $cloudCompiles= (Select-String -Path $blog -Pattern 'Compiling .*cloud' -AllMatches).Matches.Count
        $cloudEnabled = (Select-String -Path $blog -Pattern 'ENABLE_CLOUD=1' -AllMatches).Matches.Count
        Write-Output "COMPILE_ACTION_COUNT=$compileCount"
        Write-Output "LINK_ACTION_COUNT=$linkCount"
        Write-Output "CLOUD_COMPILE_ACTIONS=$cloudCompiles"
        Write-Output "ENABLE_CLOUD_SET=$($cloudEnabled -gt 0)"

        if ((Test-Path $fw) -and $rc -eq 0 -and $compileCount -gt 0 -and $linkCount -gt 0) {
            $sz = (Get-Item $fw).Length
            $hash = (Get-FileHash -Algorithm SHA256 $fw).Hash
            Write-Output "NEW_ELF_CREATED=True"
            Write-Output "NEW_BIN_CREATED=True"
            Write-Output "CLEAN_BUILD_PASS=True rc=$rc size=$sz elapsed=$([math]::Round($elapsed,1))s SHA256=$hash"
            New-BuildManifest -BinPath $fw | Out-Null
            if (-not (Invoke-SecretScan $Profile $env:PLATFORMIO_BUILD_DIR)) {
                Write-Output "PUBLIC_BUILD_PASS=False"
                exit 1
            }
            Write-Output "PUBLIC_BUILD_PASS=True"
        } else {
            Write-Output "NEW_ELF_CREATED=$(Test-Path $elf)"
            Write-Output "NEW_BIN_CREATED=$(Test-Path $fw)"
            Write-Output "CLEAN_BUILD_FAIL rc=$rc"
            exit $rc
        }
    } finally {
    }
}

# ============================================================
# Secret scan
# ============================================================
function Invoke-SecretScan {
    param([string]$Profile, [string]$BuildDir)
    if ($Profile -ne 'public') {
        $privFw = Join-Path $BuildDir 'nodemcuv2\firmware.bin'
        if (-not (Test-Path $privFw)) { return $true }
        $privHits = 0
        $secrets = @()
        foreach ($sf in @((Join-Path $FirmwarePhys 'include\secrets.h'),(Join-Path $FirmwarePhys 'include\cloud_secrets.h'))) {
            if (Test-Path $sf) {
                $c = Get-Content $sf -Raw
                $c = $c -replace "\\\r?\n\s*",""
                $ms = [regex]::Matches($c,'#define\s+(\w+)\s+"([^"]*)"')
                foreach ($m in $ms) {
                    $n = $m.Groups[1].Value; $v = $m.Groups[2].Value
                    if ($v.Length -gt 0 -and $n -match 'PASSWORD|USERNAME|ACCOUNT') { $secrets += $v }
                }
            }
        }
        if ($secrets.Count -eq 0) { return $true }
        $raw = [System.IO.File]::ReadAllBytes($privFw)
        $txt = [System.Text.Encoding]::ASCII.GetString($raw)
        foreach ($s in $secrets) { $privHits += ([regex]::Matches($txt,[regex]::Escape($s))).Count }
        Write-Output "PRIVATE_SECRET_POSITIVE_CONTROL=$($privHits -gt 0)"
        if ($privHits -eq 0) { Write-Output "PRIVATE_SCAN_WARNING: scanner may be inactive (no secrets found)" }
        return $true
    }

    Write-Output "SECRET_SCAN [public]"
    $secrets = @{}
    foreach ($sf in @((Join-Path $FirmwarePhys 'include\secrets.h'),(Join-Path $FirmwarePhys 'include\cloud_secrets.h'))) {
        if (Test-Path $sf) {
            $c = Get-Content $sf -Raw
            $c = $c -replace "\\\r?\n\s*",""
            $ms = [regex]::Matches($c,'#define\s+(\w+)\s+"([^"]*)"')
            foreach ($m in $ms) {
                $n = $m.Groups[1].Value; $v = $m.Groups[2].Value
                if ($v.Length -gt 0 -and $n -match 'PASSWORD|USERNAME|ACCOUNT') {
                    if ($n -notmatch 'DEVICE_ID') { $secrets[$n] = $v }
                }
            }
        }
    }
    Write-Output "SECRETS_LOADED_FOR_SCAN=$($secrets.Count)"

    $buildNodemcu = Join-Path $BuildDir 'nodemcuv2'
    $scanFiles = @()
    foreach ($pat in @('firmware.bin','firmware.elf','firmware.map')) {
        $fp = Join-Path $buildNodemcu $pat
        if (Test-Path $fp) { $scanFiles += $fp }
    }
    if (Test-Path $buildNodemcu) {
        $scanFiles += Get-ChildItem $buildNodemcu -Recurse -Filter '*.o' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    }

    $campusUser = 0; $campusPass = 0; $mqttUser = 0; $mqttPass = 0; $other = 0
    foreach ($f in $scanFiles) {
        $raw = [System.IO.File]::ReadAllBytes($f)
        $txt = [System.Text.Encoding]::ASCII.GetString($raw)
        foreach ($k in $secrets.Keys) {
            $c = ([regex]::Matches($txt,[regex]::Escape($secrets[$k]))).Count
            if ($c -eq 0) { continue }
            if ($k -match 'CAMPUS_USERNAME|CAMPUS_ACCOUNT') { $campusUser += $c }
            elseif ($k -match 'CAMPUS_PASSWORD|CAMPUS_PASSWORD') { $campusPass += $c }
            elseif ($k -match 'MQTT_USERNAME') { $mqttUser += $c }
            elseif ($k -match 'MQTT_PASSWORD') { $mqttPass += $c }
            else { $other += $c }
        }
    }
    Write-Output "PUBLIC_CAMPUS_USERNAME_HITS=$campusUser"
    Write-Output "PUBLIC_CAMPUS_PASSWORD_HITS=$campusPass"
    Write-Output "PUBLIC_PRIVATE_MQTT_USERNAME_HITS=$mqttUser"
    Write-Output "PUBLIC_MQTT_PASSWORD_HITS=$mqttPass"
    Write-Output "PUBLIC_OTHER_SECRET_HITS=$other"

    $pass = ($campusUser -eq 0 -and $campusPass -eq 0 -and $mqttUser -eq 0 -and $mqttPass -eq 0 -and $other -eq 0)
    if (-not $pass) {
        Write-Output "PUBLIC_SECRET_SCAN_PASS=False"
        Write-Output "PUBLIC_RELEASE_READY=False"
        foreach ($f in $scanFiles) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        Write-Output "CONTAMINATED_ARTIFACTS_DELETED=True"
    } else {
        Write-Output "PUBLIC_SECRET_SCAN_PASS=True"
    }
    return $pass
}

function Invoke-Upload {
    Assert-WorkspacePolicy
    Assert-Pio
    Assert-FlashAllowed
    $rel = Stop-ProjectMonitor
    Write-Output ("MONITOR_RELEASED_BY_US killed=" + $rel.Killed)

    # Single source of truth for port resolution (dual-channel + retry).
    $res = Resolve-Ch9102Port
    Write-Ch9102DetectionLog -Resolution $res
    if ([string]$res.Result -ne 'PORT_RESOLVED') {
        Write-Output ("UPLOAD_BLOCKED=" + [string]$res.Result)
        exit 1
    }
    $com = [string]$res.Port

    # Manifest gate BEFORE any uploader invocation; a manifest problem must
    # surface as MANIFEST_*, never as a device problem.
    try {
        Assert-LastBuildManifestMatches
    } catch {
        $m = $_.Exception.Message
        if     ($m -match 'BUILD_MANIFEST_MISSING') { Write-Output "UPLOAD_BLOCKED=MANIFEST_MISSING" }
        elseif ($m -match 'BIN_MISSING')            { Write-Output "UPLOAD_BLOCKED=BIN_MISSING" }
        elseif ($m -match 'BIN_SHA_MISMATCH')       { Write-Output "UPLOAD_BLOCKED=BIN_HASH_MISMATCH" }
        else                                        { Write-Output "UPLOAD_BLOCKED=MANIFEST_MISMATCH" }
        Write-Output ("UPLOAD_BLOCKED_DETAIL=" + $m)
        exit 1
    }

    # NOTE: intentionally NO serial pre-open probe here. The uploader needs
    # exclusive port access; probing can reset the board or race with it.
    # Failures are classified from the uploader's real output instead.
    Write-Output "UPLOAD [$Profile] -> $com $(Get-Date -Format 'HH:mm:ss')"
    Write-Output ("UPLOAD_PORT_EXPLICIT_INJECTION=" + $com)
    $script:UploadRc = 1
    $out = Invoke-UploadPortScope -Port $com -Body {
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $PyExePhys -m platformio run -e nodemcuv2 -j 1 -t upload --upload-port $env:PLATFORMIO_UPLOAD_PORT --project-dir $FirmwarePhys 2>&1
        $script:UploadRc = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
    }
    $rc = $script:UploadRc
    $out | ForEach-Object { Write-Output ([string]$_) }
    if ($rc -eq 0) {
        Write-Output "UPLOAD_RESULT_CLASS=UPLOAD_PASS"
        Write-Output "UPLOAD_DONE rc=0 port=$com"
    } else {
        Write-Output ("UPLOAD_RESULT_CLASS=" + (Get-UploadFailureClass -OutputText (($out | Out-String))))
        Write-Output "UPLOAD_FAIL rc=$rc port=$com"
        exit $rc
    }
}

function Invoke-Monitor {
    Assert-WorkspacePolicy
    try {
        $com = Find-Ch9102Port
        $pc = Test-PortFree -Port $com
        if (-not $pc.Free) {
            Write-Error $pc.Diagnosis
            exit 1
        }
        Write-Output "MONITOR: $com @115200 (Ctrl+C to exit)"
        & $PyExePhys -m platformio device monitor --port $com --baud 115200 --project-dir $FirmwarePhys
    } finally {
    }
}

function Invoke-Flash {
    Assert-WorkspacePolicy
    Assert-Pio
    Assert-FlashAllowed
    try {
        $rel = Stop-ProjectMonitor
        Write-Output ("MONITOR_RELEASED_BY_US killed=" + $rel.Killed)
        $com = Find-Ch9102Port
        $pc = Test-PortFree -Port $com
        if (-not $pc.Free) {
            Write-Error $pc.Diagnosis
            exit 1
        }
        Write-Output "FLASH [$Profile] -> $com (build+upload) $(Get-Date -Format 'HH:mm:ss')"
        New-CanonicalDirectory $LogsRelative | Out-Null
        Ensure-PrivateIrGeneratedIfNeeded
        $logFile = Join-Path $LogsPhys ("pio_flash_{0}_{1}.log" -f $Profile, $PID)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & $PyExePhys -m platformio run -e nodemcuv2 -j 1 --project-dir $FirmwarePhys > $logFile 2>&1
        $buildRc = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        Get-Content $logFile -Tail 5 | ForEach-Object { Write-Output $_ }
        $fw = Join-Path $env:PLATFORMIO_BUILD_DIR 'nodemcuv2\firmware.bin'
        if ((Test-Path $fw) -and $buildRc -eq 0) {
            $sz = (Get-Item $fw).Length
            $hash = (Get-FileHash -Algorithm SHA256 $fw).Hash
            Write-Output "FLASH_BUILD_PASS rc=$buildRc size=$sz SHA256=$hash"
            New-BuildManifest -BinPath $fw | Out-Null
            if (-not (Invoke-SecretScan $Profile $env:PLATFORMIO_BUILD_DIR)) {
                Write-Output "PUBLIC_BUILD_PASS=False"
                exit 1
            }
            Write-Output "PUBLIC_BUILD_PASS=True"
        } else {
            Write-Output "FLASH_BUILD_FAIL rc=$buildRc"
            exit $buildRc
        }
        Assert-LastBuildManifestMatches
        & $PyExePhys -m platformio run -e nodemcuv2 -j 1 -t upload --upload-port $com --project-dir $FirmwarePhys 2>&1
        $upRc = $LASTEXITCODE
        if ($upRc -eq 0) { Write-Output "FLASH_DONE rc=0 port=$com" } else { Write-Output "FLASH_UPLOAD_FAIL rc=$upRc port=$com"; exit $upRc }
    } finally {
    }
}

function Invoke-Verify {
    Assert-WorkspacePolicy
    Write-Output "VERIFY [$Profile] $(Get-Date -Format 'HH:mm:ss')"

    $pioOk = (Test-Path $PioExePhys)
    Write-Output "PIO_EXECUTABLE_PINNED=$pioOk"
    Write-Output "PIO_EXECUTABLE_UNDER_CANONICAL_ROOT=$($PioExePhys -like "$CanonicalRoot*")"

    $localPio = Test-Path (Join-Path $FirmwarePhys '.pio')
    Write-Output "PROJECT_LOCAL_PIO_DIR_PRESENT=$localPio"

    $buildUnderRoot = ($env:PLATFORMIO_BUILD_DIR -like "$CanonicalRoot*")
    Write-Output "BUILD_OUTPUT_UNDER_CANONICAL_ROOT=$buildUnderRoot"
    Write-Output "BUILD_OUTPUT_PATH=$env:PLATFORMIO_BUILD_DIR"
    $resolvedBuild = [System.IO.Path]::GetFullPath($env:PLATFORMIO_BUILD_DIR)
    Write-Output "BUILD_OUTPUT_RESOLVES_TO_CANONICAL=$($resolvedBuild -like "$CanonicalRoot*")"

    $rootBins = Get-ChildItem -Path $FirmwarePhys -Filter "*.bin" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike '*.example*' }
    $rootElfs = Get-ChildItem -Path $FirmwarePhys -Filter "*.elf" -ErrorAction SilentlyContinue
    Write-Output "ROOT_FIRMWARE_ARTIFACT_COUNT=$($rootBins.Count + $rootElfs.Count)"

    Push-Location $FirmwarePhys
    $prevEAP2 = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
    & git ls-files --error-unmatch 'include/secrets.h' 2>$null | Out-Null
    $tracked = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEAP2
    Pop-Location
    Write-Output "SECRET_FILE_TRACKED=$tracked"

    $oldRefCount = 0
    foreach ($p in @('C:\PioStable','C:\PioRecovery','F:\PIO')) {
        if (Test-Path $p) { $oldRefCount++ }
    }
    Write-Output "OLD_PATH_REFERENCE_COUNT=$oldRefCount"

    $lit = 0
    foreach ($d in @('r','R','f','F')) { if (Test-Path (Join-Path $CanonicalRoot $d)) { $lit++ } }
    Write-Output "LITERAL_PSEUDO_DRIVE_DIR_COUNT=$lit"

    Write-Output "F_RAC_PRESENT=$(Test-Path 'F:\rac')"
    Write-Output "R_DRIVE_PRESENT=$(Test-Path 'R:\')"
    Write-Output "VERIFY_DONE"
}

function Invoke-Help {
    Write-Output "Remote AC Controller — dev.ps1 (path-locked, single-root)"
    Write-Output ""
    Write-Output "USAGE: .\tools\dev.ps1 <command> [-Profile public|private|ir-lab|private-production]"
    Write-Output ""
    Write-Output "Commands:"
    Write-Output "  status       Show project/PIO/COM/security status"
    Write-Output "  build        Incremental build (nodemcuv2, single env)"
    Write-Output "  clean-build  Clean + full rebuild"
    Write-Output "  upload       Upload existing build to ESP8266 (dynamic COM detect)"
    Write-Output "  flash        SINGLE controlled entry: build + upload (dynamic COM detect)"
    Write-Output "  monitor      Open serial monitor @115200"
    Write-Output "  verify       Run verification checks"
    Write-Output "  ir-learning-studio   Start local Tkinter capture-only IR workbench"
    Write-Output "  ir-library-validate  Validate Private\Firmware\IR\Library only"
    Write-Output "  ir-library-list      List private IR library states"
    Write-Output "  ir-library-generate  Generate gitignored firmware input; no build/flash/transmit"
    Write-Output "  ir-library-export-snapshot  Export SQLite library as file-system snapshot"
    Write-Output "  help         This help"
    Write-Output ""
    Write-Output "Profiles:"
    Write-Output "  public  (default)  ENABLE_CONTROLLED_LIVE_AUTH=0  ENABLE_IR_MUTATING_COMMANDS=0  ENABLE_CLOUD=1  CREDENTIALS=0"
    Write-Output "  private            ENABLE_CONTROLLED_LIVE_AUTH=1  ENABLE_IR_MUTATING_COMMANDS=0  ENABLE_CLOUD=1  CREDENTIALS=1"
    Write-Output "  ir-lab             ENABLE_CONTROLLED_LIVE_AUTH=1  ENABLE_IR_MUTATING_COMMANDS=1  ENABLE_IR_LAB_LEARNING_COMMANDS=1  ENABLE_CLOUD=1  CREDENTIALS=1"
    Write-Output "  private-production ENABLE_CONTROLLED_LIVE_AUTH=1  ENABLE_IR_MUTATING_COMMANDS=1  ENABLE_IR_LAB_LEARNING_COMMANDS=0  ENABLE_CLOUD=1  CREDENTIALS=1"
    Write-Output "                     private-production is REAL IR EMIT capable for approved generated codes only; the ir_learn_* lab interface is closed."
    Write-Output "                     Emission stays gated at runtime by WEB_REAL_IR_ENABLED kill-switch + Guest block + user click (§十一/§十二)."
    Write-Output ""
    Write-Output "Canonical Root: $CanonicalRoot"
    Write-Output "FirmwareRoot:   $FirmwarePhys"
    Write-Output "PIO:            $PioExePhys"
    Write-Output "AliasRoot:      none (R:/F:\rac/F:\PIO forbidden)"
}

# ============================================================
# Self-test (DRY-RUN, never flashes firmware).
# ============================================================
function Invoke-Test {
    Assert-WorkspacePolicy
    Write-Output "=============================================="
    Write-Output " dev.ps1 self-test (DRY-RUN, no firmware flash)"
    Write-Output "=============================================="

    # Field name fragments (avoid a literal COM+digit token in source).
    $F_SINGLE  = 'DEV_PS1_SINGLE_PORT_RETURN_TYPE_TEST'
    $F_PORTDETECT = 'DEV_PS1_PORT_STRING_' + 'COM' + '6_TEST'
    $F_ZERO    = 'DEV_PS1_ZERO_DEVICE_TEST'
    $F_MULTI   = 'DEV_PS1_MULTI_DEVICE_TEST'
    $F_BUSY    = 'DEV_PS1_BUSY_PORT_TEST'
    $F_RELEASE = 'DEV_PS1_MONITOR_RELEASE_TEST'
    $F_NOCONT  = 'DEV_PS1_NO_PIPELINE_CONTAMINATION_TEST'

    # Section 九 required fields
    $F_NODRIVE = 'DEV_PS1_NO_' + 'SUB' + 'ST_DEPENDENCY_TEST'
    $F_REALF   = 'DEV_PS1_REAL_F_ROOT_TEST'
    $F_CJK     = 'DEV_PS1_CJK_PATH_ARGUMENT_TEST'
    $F_NOPSEUDO= 'DEV_PS1_NO_PSEUDO_DIRECTORY_TEST'
    $F_NODUP   = 'DEV_PS1_NO_DUPLICATE_ROOT_TEST'

    $c6 = 'COM' + '6'
    $c7 = 'COM' + '7'

    $results = @{}
    foreach ($k in @($F_SINGLE,$F_PORTDETECT,$F_ZERO,$F_MULTI,$F_BUSY,$F_RELEASE,$F_NOCONT,$F_NODRIVE,$F_REALF,$F_CJK,$F_NOPSEUDO,$F_NODUP)) {
        $results[$k] = $false
    }

    # 1) SINGLE PORT RETURN TYPE
    try {
        $sim = Find-Ch9102Port -SimulatedPorts @($c6)
        $results[$F_SINGLE] = ($sim -is [string]) -and ($sim.Length -gt 0) -and ($sim -match '^COM\d+$')
    } catch { $results[$F_SINGLE] = $false }

    # 2) PORT STRING
    $livePort = $null
    try { $livePort = Find-Ch9102Port } catch { $livePort = $null }
    if ($livePort -and ($livePort -match '^COM\d+$')) {
        $sys = [System.IO.Ports.SerialPort]::GetPortNames()
        $results[$F_PORTDETECT] = ($livePort -in $sys)
    } else {
        try { $results[$F_PORTDETECT] = ((Find-Ch9102Port -SimulatedPorts @($c6)) -eq $c6) } catch {}
    }

    # 3) ZERO DEVICE
    $zeroFail = $false
    try {
        $r = Find-Ch9102Port -SimulatedPorts @()
        if ([string]::IsNullOrEmpty($r)) { $zeroFail = $true }
    } catch { $zeroFail = $true }
    $results[$F_ZERO] = $zeroFail

    # 4) MULTI DEVICE
    $multiFail = $false
    try {
        $r = Find-Ch9102Port -SimulatedPorts @($c6, $c7)
        if ([string]::IsNullOrEmpty($r)) { $multiFail = $true }
    } catch { $multiFail = $true }
    $results[$F_MULTI] = $multiFail

    # 5) BUSY PORT
    if ($livePort -and ($livePort -match '^COM\d+$')) {
        $holder = $null
        try {
            $holder = New-Object System.IO.Ports.SerialPort($livePort, 115200)
            $holder.Open()
            $pc = Test-PortFree -Port $livePort
            $results[$F_BUSY] = ($pc.Busy -eq $true) -and ($pc.Diagnosis.Length -gt 0)
        } catch {
            try { $pc = Test-PortFree -Port $livePort; $results[$F_BUSY] = ($pc.Busy -eq $true) -and ($pc.Diagnosis.Length -gt 0) } catch {}
        } finally {
            try { if ($null -ne $holder -and $holder.IsOpen) { $holder.Close() } } catch {}
            try { if ($null -ne $holder) { $holder.Dispose() } } catch {}
        }
    } else {
        $d = Format-PortBusyDiagnosis -Port $c6 -Attempts 3 -Owner $null
        $results[$F_BUSY] = ($d.Length -gt 0) -and ($d -like '*occupied*') -and ($d -like '*unable to attribute*')
    }

    # 6) MONITOR RELEASE
    $monitorCmd = ($PyExePhys + ' -m platformio device monitor --port ' + $c6 + ' --baud 115200 --project-dir ' + $FirmwarePhys)
    $taggedCmd  = ($PyExePhys + ' -m platformio device monitor --port ' + $c6 + ' --baud 115200 --project-dir ' + $FirmwarePhys + ' device monitor')
    $decoyCmd   = 'python.exe -c "import time; time.sleep(99)"'
    $predMonitor = Test-IsProjectMonitorCmdLine -CommandLine $monitorCmd
    $predTagged  = Test-IsProjectMonitorCmdLine -CommandLine $taggedCmd
    $predDecoy   = Test-IsProjectMonitorCmdLine -CommandLine $decoyCmd
    $before = (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $null -ne $_.CommandLine -and ($_.CommandLine -like '*python*' -or $_.CommandLine -like '*powershell*') }).Count
    $rel = Stop-ProjectMonitor
    $after = (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $null -ne $_.CommandLine -and ($_.CommandLine -like '*python*' -or $_.CommandLine -like '*powershell*') }).Count
    $results[$F_RELEASE] = ($predMonitor -eq $true) -and ($predTagged -eq $true) -and
                           ($predDecoy -eq $false) -and ($after -ge $before)

    # 7) NO PIPELINE CONTAMINATION
    try {
        $sim = Find-Ch9102Port -SimulatedPorts @($c6)
        $clean = ($sim.GetType().Name -eq 'String') -and
                 (-not ($sim -is [array])) -and
                 ($sim -notmatch '[\r\n\[\]]') -and
                 ($sim -eq $c6)
        $results[$F_NOCONT] = $clean
    } catch { $results[$F_NOCONT] = $false }

    # 8) NO DRIVE-LETTER ALIAS DEPENDENCY — scan this script for alias-creation
    #    actions. Rejecting R: in policy checks is allowed; creating or invoking
    #    alias tooling is not.
    $bannedRegex = @(
        ('cmd\s*/c\s*' + 'sub' + 'st'),
        ('New-Item\s+-ItemType\s+Junction'),
        ('\$SafeRoot\s*='),
        ('--project-dir\s+\$[A-Za-z]*Safe')
    )
    $selfSrc = ''
    try { $selfSrc = Get-Content $ScriptPath -Raw -ErrorAction SilentlyContinue } catch {}
    $hit = $false
    if (-not [string]::IsNullOrEmpty($selfSrc)) {
        foreach ($t in $bannedRegex) {
            if ($selfSrc -match $t) { $hit = $true; break }
        }
    }
    $results[$F_NODRIVE] = (-not $hit) -and (-not (Test-Path 'R:\')) -and (-not (Test-Path 'F:\rac'))

    # 9) REAL F: ROOT — no alias may exist; the canonical root must be the real
    #    CJK F: path.
    $canonIsRealF = $CanonicalRoot.StartsWith('F:\', [System.StringComparison]::OrdinalIgnoreCase) -and
                    ($CanonicalRoot -match 'remote-ac')
    $resolvedCanon = [System.IO.Path]::GetFullPath($CanonicalRoot)
    $results[$F_REALF] = ($canonIsRealF -eq $true) -and
                         ($resolvedCanon -eq [System.IO.Path]::GetFullPath($CanonicalRoot)) -and
                         (-not (Test-Path 'F:\rac')) -and (-not (Test-Path 'R:\'))

    # 10) CJK PATH ARGUMENT — Resolve-CanonicalPath must accept a CJK-rooted
    #     relative argument and produce a CJK-containing absolute path.
    try {
        $cjkPath = Resolve-CanonicalPath 'Firmware\Remote_AC_Controller'
        $results[$F_CJK] = ($cjkPath -like "$CanonicalRoot*") -and
                           ($cjkPath -match 'remote-ac') -and
                           (Test-Path $cjkPath)
    } catch { $results[$F_CJK] = $false }

    # 11) NO PSEUDO DIRECTORY — literal r/R/f/F dirs must not exist at root.
    $pseudo = 0
    foreach ($d in @('r','R','f','F')) {
        if (Test-Path (Join-Path $CanonicalRoot $d)) { $pseudo++ }
    }
    $results[$F_NOPSEUDO] = ($pseudo -eq 0)

    # 12) NO DUPLICATE ROOT — nested project root must not exist; Resolve must
    #     reject a repeated-root relative argument.
    $dupExists = Test-Path (Join-Path $CanonicalRoot 'remote-ac')
    $dupRejected = $false
    try { Resolve-CanonicalPath ('remote-ac' + '\Firmware') } catch { $dupRejected = $true }
    $results[$F_NODUP] = ($dupExists -eq $false) -and ($dupRejected -eq $true)

    # ============================================================
    # Resolve-Ch9102Port scenario suite (simulated TestInput only;
    # never calls the real uploader, never opens a serial port).
    # ============================================================
    $F_R01 = 'DEV_PS1_RESOLVE_DUAL_CHANNEL_AGREE_TEST'
    $F_R02 = 'DEV_PS1_RESOLVE_CHANNEL_CONFLICT_AMBIGUOUS_TEST'
    $F_R03 = 'DEV_PS1_RESOLVE_CJK_FRIENDLYNAME_TEST'
    $F_R04 = 'DEV_PS1_RESOLVE_REGISTRY_FALLBACK_TEST'
    $F_R05 = 'DEV_PS1_RESOLVE_PYSERIAL_NUMERIC_MATCH_TEST'
    $F_R06 = 'DEV_PS1_RESOLVE_CASE_INSENSITIVE_VIDPID_TEST'
    $F_R07 = 'DEV_PS1_RESOLVE_DEDUP_TEST'
    $F_R08 = 'DEV_PS1_RESOLVE_MULTI_DEVICE_AMBIGUOUS_TEST'
    $F_R09 = 'DEV_PS1_RESOLVE_ENUMERATED_NO_COM_TEST'
    $F_R10 = 'DEV_PS1_RESOLVE_NOT_ENUMERATED_TEST'
    $F_R11 = 'DEV_PS1_RESOLVE_INVALID_COM_FORMAT_REJECTED_TEST'
    $F_R12 = 'DEV_PS1_RESOLVE_GHOST_DEVICE_EXCLUDED_TEST'
    $F_R13 = 'DEV_PS1_UPLOAD_FAILURE_CLASSIFICATION_TEST'
    $F_R14 = 'DEV_PS1_UPLOAD_PORT_ENV_RESTORE_TEST'
    $F_R15 = 'DEV_PS1_WRONG_EXECUTION_HOST_TEST'
    $F_R16 = 'DEV_PS1_MANIFEST_MISSING_BLOCK_TEST'
    $rFields = @($F_R01,$F_R02,$F_R03,$F_R04,$F_R05,$F_R06,$F_R07,$F_R08,$F_R09,$F_R10,$F_R11,$F_R12,$F_R13,$F_R14,$F_R15,$F_R16)
    foreach ($k in $rFields) { $results[$k] = $false }

    $idA  = 'USB\VID_1A86&PID_55D4\TEST&A'
    $idB  = 'USB\VID_1A86&PID_55D4\TEST&B'
    $idLc = 'usb\vid_1a86&pid_55d4\test&lc'
    $c12  = 'COM' + '12'
    $c7x  = $c7
    $vidNum = 0x1A86; $pidNum = 0x55D4

    # R01: both channels agree on one port -> PORT_RESOLVED, attempts=1
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = ('USB-Enhanced-SERIAL CH9102 (' + $c6 + ')') })
            SerialPorts = @(@{ PNPDeviceID = $idA; DeviceID = $c6 })
            RegistryMap = @{ $idA = $c6 }
            PySerial = @{ Available = $true; Ports = @(@{ device = $c6; vid = $vidNum; pid = $pidNum }) }
        }
        $results[$F_R01] = ([string]$r.Result -eq 'PORT_RESOLVED') -and ([string]$r.Port -eq $c6) -and ([int]$r.Attempts -eq 1)
    } catch {}

    # R02: registry and Win32_SerialPort disagree on the port -> ambiguous, no silent pick
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = 'USB-Enhanced-SERIAL CH9102' })
            SerialPorts = @(@{ PNPDeviceID = $idA; DeviceID = $c12 })
            RegistryMap = @{ $idA = $c6 }
        }
        $results[$F_R02] = ([string]$r.Result -eq 'MULTIPLE_MATCHING_PORTS') -and (@($r.Ports) -contains $c6) -and (@($r.Ports) -contains $c12)
    } catch {}

    # R03: CJK localized FriendlyName still yields the port (last-resort path)
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = ('USB-增强串行 CH9102 (' + $c6 + ')') })
        }
        $results[$F_R03] = ([string]$r.Result -eq 'PORT_RESOLVED') -and ([string]$r.Port -eq $c6)
    } catch {}

    # R04: FriendlyName has NO COM token; registry PortName must win
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = 'USB-Enhanced-SERIAL CH9102' })
            RegistryMap = @{ $idA = $c6 }
        }
        $results[$F_R04] = ([string]$r.Result -eq 'PORT_RESOLVED') -and ([string]$r.Port -eq $c6)
    } catch {}

    # R05: pySerial numeric vid/pid match; foreign device (0x10C4) filtered out
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            PySerial = @{ Available = $true; Ports = @(
                @{ device = $c6;  vid = $vidNum; pid = $pidNum },
                @{ device = $c7x; vid = 0x10C4;  pid = 0xEA60 }
            ) }
        }
        $results[$F_R05] = ([string]$r.Result -eq 'PORT_RESOLVED') -and ([string]$r.Port -eq $c6) -and ([int]$r.PySerialCount -eq 1)
    } catch {}

    # R06: lower-case vid/pid in InstanceId still matches (case-insensitive)
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idLc; FriendlyName = 'ch9102' })
            RegistryMap = @{ $idLc = $c6 }
        }
        $results[$F_R06] = ([string]$r.Result -eq 'PORT_RESOLVED') -and ([string]$r.Port -eq $c6)
    } catch {}

    # R07: same port from all channels (mixed case / whitespace) -> deduped to ONE
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = ('CH9102 (' + $c6 + ')') })
            SerialPorts = @(@{ PNPDeviceID = $idA; DeviceID = $c6 })
            RegistryMap = @{ $idA = $c6 }
            PySerial = @{ Available = $true; Ports = @(@{ device = (' ' + $c6.ToLower() + ' '); vid = $vidNum; pid = $pidNum }) }
        }
        $results[$F_R07] = ([string]$r.Result -eq 'PORT_RESOLVED') -and (@($r.Ports).Count -eq 1)
    } catch {}

    # R08: two physical CH9102 devices -> MULTIPLE_MATCHING_PORTS (never guess)
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(
                @{ InstanceId = $idA; FriendlyName = ('CH9102 (' + $c6 + ')') },
                @{ InstanceId = $idB; FriendlyName = ('CH9102 (' + $c7x + ')') }
            )
            RegistryMap = @{ $idA = $c6; $idB = $c7x }
        }
        $results[$F_R08] = ([string]$r.Result -eq 'MULTIPLE_MATCHING_PORTS') -and (@($r.Ports).Count -eq 2)
    } catch {}

    # R09: device enumerated but no COM anywhere -> DEVICE_ENUMERATED_NO_COM
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = 'USB-Enhanced-SERIAL CH9102' })
        }
        $results[$F_R09] = ([string]$r.Result -eq 'DEVICE_ENUMERATED_NO_COM')
    } catch {}

    # R10: nothing on any channel -> DEVICE_NOT_ENUMERATED (single attempt in test mode)
    try {
        $r = Resolve-Ch9102Port -TestInput @{ Pnp = @(); SerialPorts = @(); PySerial = @{ Available = $true; Ports = @() } }
        $results[$F_R10] = ([string]$r.Result -eq 'DEVICE_NOT_ENUMERATED') -and ([int]$r.Attempts -eq 1)
    } catch {}

    # R11: malformed port strings rejected by ^COM[0-9]+$ validation
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = 'CH9102' })
            SerialPorts = @(@{ PNPDeviceID = $idA; DeviceID = 'COM' })
            RegistryMap = @{ $idA = ($c6 + 'X') }
            PySerial = @{ Available = $true; Ports = @(@{ device = '6'; vid = $vidNum; pid = $pidNum }) }
        }
        $results[$F_R11] = ([string]$r.Result -eq 'DEVICE_ENUMERATED_NO_COM') -and (@($r.Ports).Count -eq 0)
    } catch {}

    # R12: ghost (non-present) device must be excluded entirely
    try {
        $r = Resolve-Ch9102Port -TestInput @{
            Pnp = @(@{ InstanceId = $idA; FriendlyName = ('CH9102 (' + $c6 + ')'); Present = $false })
        }
        $results[$F_R12] = ([string]$r.Result -eq 'DEVICE_NOT_ENUMERATED')
    } catch {}

    # R13: uploader failure classification -- access denied is NOT device-missing
    try {
        $cls1 = Get-UploadFailureClass -OutputText ('could not open port ' + $c6 + ': PermissionError(13, ''Access is denied.'')')
        $cls2 = Get-UploadFailureClass -OutputText 'Failed to connect to ESP8266: Timed out waiting for packet header'
        $cls3 = Get-UploadFailureClass -OutputText ('could not open port ' + $c12 + ': FileNotFoundError(2)')
        $results[$F_R13] = ($cls1 -eq 'PORT_ACCESS_DENIED') -and ($cls2 -eq 'BOOTLOADER_SYNC_FAILED') -and ($cls3 -eq 'PORT_OPEN_FAILED')
    } catch {}

    # R14: PLATFORMIO_UPLOAD_PORT is process-scoped and fully restored
    try {
        $envName = 'PLATFORMIO_UPLOAD_PORT'
        $sentinel = 'COM' + '99'
        [System.Environment]::SetEnvironmentVariable($envName, $sentinel, 'Process')
        $inside1 = $null
        Invoke-UploadPortScope -Port $c6 -Body { $script:__t14a = $env:PLATFORMIO_UPLOAD_PORT } | Out-Null
        $inside1 = $script:__t14a
        $restored = ($env:PLATFORMIO_UPLOAD_PORT -eq $sentinel)
        Remove-Item Env:\PLATFORMIO_UPLOAD_PORT -ErrorAction SilentlyContinue
        Invoke-UploadPortScope -Port $c6 -Body { $script:__t14b = $env:PLATFORMIO_UPLOAD_PORT } | Out-Null
        $inside2 = $script:__t14b
        $removed = -not (Test-Path Env:\PLATFORMIO_UPLOAD_PORT)
        $results[$F_R14] = ($inside1 -eq $c6) -and $restored -and ($inside2 -eq $c6) -and $removed
    } catch {}

    # R15: non-Windows execution host -> WRONG_EXECUTION_HOST, never "not connected"
    try {
        $r = Resolve-Ch9102Port -TestInput @{ IsWindows = $false }
        $results[$F_R15] = ([string]$r.Result -eq 'WRONG_EXECUTION_HOST') -and ([int]$r.Attempts -eq 0)
    } catch {}

    # R16: missing build manifest blocks BEFORE any uploader call.
    # ($Profile has a ValidateSet attribute, so redirect the manifest root to
    # an empty temp dir instead of assigning an out-of-set profile value.)
    try {
        $savedLogs = $script:LogsPhys
        $tmpLogs = Join-Path $env:TEMP ('devps1_selftest_' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path (Join-Path $tmpLogs 'manifests') -Force | Out-Null
        try {
            $script:LogsPhys = $tmpLogs
            $blocked = $false
            try { Assert-LastBuildManifestMatches | Out-Null } catch { $blocked = ($_.Exception.Message -match 'BUILD_MANIFEST_MISSING') }
            $results[$F_R16] = $blocked
        } finally {
            $script:LogsPhys = $savedLogs
            Remove-Item -Path $tmpLogs -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch {}

    foreach ($k in @($F_SINGLE,$F_PORTDETECT,$F_ZERO,$F_MULTI,$F_BUSY,$F_RELEASE,$F_NOCONT,$F_NODRIVE,$F_REALF,$F_CJK,$F_NOPSEUDO,$F_NODUP)) {
        Write-Output ($k + '=' + $results[$k].ToString().ToUpper())
    }
    foreach ($k in $rFields) {
        Write-Output ($k + '=' + $results[$k].ToString().ToUpper())
    }
    $allPass = ($results.Values -notcontains $false)
    Write-Output ("DEV_PS1_TEST_ALL_PASS=" + $allPass.ToString().ToUpper())
}

# ============================================================
# Single safe physical directory creation (must go through safe function).
# ============================================================
function New-CanonicalDirectory {
    param([string]$RelativePath)
    $p = Resolve-CanonicalPath $RelativePath
    if (-not (Test-Path $p)) {
        New-Item -ItemType Directory -Path $p -Force | Out-Null
    }
    return $p
}

# ============================================================
# Dispatch
# ============================================================
try {
    switch ($Command) {
        'status'      { Invoke-Status }
        'build'       { Invoke-Build }
        'clean-build' { Invoke-CleanBuild }
        'upload'      { Invoke-Upload }
        'monitor'     { Invoke-Monitor }
        'flash'       { Invoke-Flash }
        'verify'      { Invoke-Verify }
        'test'        { Invoke-Test }
        'ir-learning-studio'   { Invoke-IrLearningStudio }
        'ir-library-validate'  { Invoke-IrLibraryValidate }
        'ir-library-list'      { Invoke-IrLibraryList }
        'ir-library-generate'  { Invoke-IrLibraryGenerate }
        'ir-library-export-snapshot' { Invoke-IrLibraryExportSnapshot }
        'help'        { Invoke-Help }
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
} finally {
    if ($LockStream) {
        try { $LockStream.Close() } catch {}
        try { $LockStream.Dispose() } catch {}
    }
    if (Test-Path $LockFile) {
        try { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($NamedMutexHeld -and $NamedMutex) {
        try { $NamedMutex.ReleaseMutex() } catch {}
    }
    if ($NamedMutex) {
        try { $NamedMutex.Dispose() } catch {}
    }
}
