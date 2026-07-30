# detect_port.ps1
# Detect the NodeMCU serial (COM) port on Windows.
#
# Combines THREE sources:
#   - pio device list        (cross-check only, timeout-guarded; never blocks)
#   - Win32_SerialPort       (WMI: COM + PNPDeviceID)
#   - Get-PnpDevice -Class Ports  (USB-UART VID/PID/FriendlyName/PnPDeviceID)
#
# Priority USB-UART signatures:
#   CH9102       VID 1A86  PID 55D4
#   CH340/CH341  VID 1A86  PID 7523 / 5523
#   CP210x       VID 10C4  (any PID)
#   FTDI         VID 0403  (any PID)
#
# Rules:
#   - COM1 is ALWAYS forbidden.
#   - Exactly one confirmed USB-UART  -> print port + details, exit 0.
#   - More than one confirmed         -> list all, exit 3 (user must choose).
#   - Zero confirmed but a generic port exists -> UNCONFIRMED_NODEMCU, exit 1
#                                      (callers MUST NOT auto-flash).
#   - No serial port at all           -> exit 2.
#
# Output contract (callers parse the first bare "COMx" line):
#   First stdout line = bare COM port (e.g. "COM6") when exactly one is confirmed.
#   Remaining lines carry structured details (PORT=/FRIENDLY_NAME=/VID=/PID=/...).

param()

$ErrorActionPreference = 'Continue'

# Ensure PlatformIO Core dir is known (fallback to persisted registry value)
if (-not $env:PLATFORMIO_CORE_DIR) {
    $env:PLATFORMIO_CORE_DIR = [Environment]::GetEnvironmentVariable('PLATFORMIO_CORE_DIR', 'User')
}
$env:NO_PROXY = (@($env:NO_PROXY -split ',' | Where-Object { $_.Trim() }) +
    @('.platformio.org', 'platformio.org', '.espressif.com', 'espressif.com') | Sort-Object -Unique) -join ','

function Get-PioExe {
    if ($env:PLATFORMIO_CORE_DIR) {
        $c = Join-Path $env:PLATFORMIO_CORE_DIR 'penv\Scripts\pio.exe'
        if (Test-Path $c) { return $c }
    }
    $onPath = Get-Command pio.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

# Known USB-UART VID/PID signatures (keyed upper-case, colon-separated)
$KnownVidPid = @{
    '1A86:55D4' = 'CH9102'
    '1A86:7523' = 'CH340/CH341'
    '1A86:5523' = 'CH340/CH341'
}
$KnownVid = @{ '10C4' = 'CP210x'; '0403' = 'FTDI' }

function Classify {
    param($vid, $devPid)
    if ($vid -and $devPid) {
        $key = "$vid`:$devPid".ToUpper()
        if ($KnownVidPid.ContainsKey($key)) { return $KnownVidPid[$key] }
    }
    if ($vid -and $KnownVid.ContainsKey($vid.ToUpper())) { return $KnownVid[$vid.ToUpper()] }
    return $null
}

# ---- Collect from PnP (primary: gives VID/PID/FriendlyName/PnPDeviceID) ----
$candidates = @()
try {
    $pnp = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue
    foreach ($d in $pnp) {
        $fn = $d.FriendlyName
        if ($fn -notmatch 'COM(\d+)') { continue }
        $com = "COM$($Matches[1])"
        if ($com -eq 'COM1') { continue }            # COM1 is forbidden
        $pnpId = $d.InstanceId
        $vid = $null; $devPid = $null
        if ($pnpId -match 'VID_([0-9A-Fa-f]{4})') { $vid = $Matches[1].ToUpper() }
        if ($pnpId -match 'PID_([0-9A-Fa-f]{4})') { $devPid = $Matches[1].ToUpper() }
        $candidates += [PSCustomObject]@{
            Port         = $com
            FriendlyName = $fn
            VID          = $vid
            DevPid       = $devPid
            PnPDeviceID  = $pnpId
            Signature    = (Classify $vid $devPid)   # non-null => confirmed USB-UART
        }
    }
} catch {
    Write-Warning "Get-PnpDevice failed: $_"
}

# ---- Enrich / cross-check with Win32_SerialPort (WMI) ----
try {
    $wmi = Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue
    foreach ($p in $wmi) {
        $com = $p.DeviceID
        if (-not $com -or $com -eq 'COM1') { continue }
        $existing = $candidates | Where-Object { $_.Port -eq $com } | Select-Object -First 1
        if (-not $existing) {
            $vid = $null; $devPid = $null
            $pnpId = $p.PNPDeviceID
            if ($pnpId -match 'VID_([0-9A-Fa-f]{4})') { $vid = $Matches[1].ToUpper() }
            if ($pnpId -match 'PID_([0-9A-Fa-f]{4})') { $devPid = $Matches[1].ToUpper() }
            $candidates += [PSCustomObject]@{
                Port         = $com
                FriendlyName = $p.Description
                VID          = $vid
                DevPid       = $devPid
                PnPDeviceID  = $pnpId
                Signature    = (Classify $vid $devPid)
            }
        }
    }
} catch {}

# ---- Cross-check with pio device list (timeout-guarded; never blocks) ----
$pio = Get-PioExe
$pioPorts = @{}
if ($pio) {
    try {
        $job = Start-Job -ScriptBlock { param($pio) & $pio device list 2>&1 } -ArgumentList $pio
        if (Wait-Job $job -Timeout 30) {
            $out = Receive-Job $job
            foreach ($line in $out) {
                if ($line -match '^(COM\d+)') { $pioPorts[$Matches[1]] = $true }
            }
        } else {
            Stop-Job $job
            Write-Warning "pio device list timed out after 30s; using PnP/WMI only"
        }
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    } catch {}
}

foreach ($c in $candidates) {
    if ($pioPorts.ContainsKey($c.Port)) { Add-Member -InputObject $c -NotePropertyName SeenByPio -NotePropertyValue $true -Force }
    else { Add-Member -InputObject $c -NotePropertyName SeenByPio -NotePropertyValue $false -Force }
}

# De-duplicate by Port (keep first occurrence)
$seen = @{}
$uniq = @()
foreach ($c in $candidates) {
    if (-not $seen.ContainsKey($c.Port)) { $seen[$c.Port] = $true; $uniq += $c }
}
$candidates = @($uniq)

$confirmed = @($candidates | Where-Object { $_.Signature })

if ($candidates.Count -eq 0) {
    Write-Output "NO_SERIAL_PORT_FOUND"
    if ($pio) { & $pio device list 2>&1 | ForEach-Object { Write-Warning "pio-device-list: $_" } }
    exit 2
}

if ($confirmed.Count -eq 1) {
    $c = $confirmed[0]
    Write-Output $c.Port
    Write-Output "PORT=$($c.Port)"
    Write-Output "FRIENDLY_NAME=$($c.FriendlyName)"
    Write-Output "VID=$($c.VID)"
    Write-Output "PID=$($c.DevPid)"
    Write-Output "PNP_DEVICE_ID=$($c.PnPDeviceID)"
    Write-Output "USB_UART_SIGNATURE=$($c.Signature)"
    Write-Output "SEEN_BY_PIO=$($c.SeenByPio)"
    Write-Output "STATUS=CONFIRMED_NODEMCU"
    exit 0
}

if ($confirmed.Count -gt 1) {
    Write-Output "MULTIPLE_CANDIDATES"
    $i = 0
    foreach ($c in $confirmed) {
        $i++
        Write-Output "CANDIDATE_${i}_PORT=$($c.Port)"
        Write-Output "CANDIDATE_${i}_FRIENDLY=$($c.FriendlyName)"
        Write-Output "CANDIDATE_${i}_VID=$($c.VID)"
        Write-Output "CANDIDATE_${i}_PID=$($c.DevPid)"
        Write-Output "CANDIDATE_${i}_PNP=$($c.PnPDeviceID)"
        Write-Output "CANDIDATE_${i}_SIGNATURE=$($c.Signature)"
    }
    Write-Output "STATUS=REQUIRE_USER_CHOICE"
    Write-Output "More than one USB-UART detected. Connect ONLY the NodeMCU, or pass -Port explicitly to upload.ps1 / smoke_test.ps1."
    exit 3
}

# Zero confirmed: only generic serial ports without a known USB-UART signature
Write-Output "UNCONFIRMED_NODEMCU"
foreach ($c in $candidates) {
    Write-Output "GENERIC_PORT=$($c.Port)"
    Write-Output "GENERIC_FRIENDLY=$($c.FriendlyName)"
    Write-Output "GENERIC_PNP=$($c.PnPDeviceID)"
}
Write-Output "STATUS=NO_USB_UART_SIGNATURE"
Write-Output "Detected serial port(s) without a known USB-UART VID/PID signature. Refusing to auto-flash."
exit 1
