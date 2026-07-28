# Verify-PlatformIOEnvironment.ps1 — READ-ONLY preflight.
# Dot-source Enter-LockedPlatformIO.ps1 before running this script.
# Default mode: read-only.  Does NOT delete, move, install, or repair files.
#
# Usage:
#   . .\tools\Enter-LockedPlatformIO.ps1
#   .\tools\Verify-PlatformIOEnvironment.ps1

param([switch]$AllowRepair, [string]$GoldenSnapshotPath)

$ErrorActionPreference = 'Continue'
$ProjectDir = 'F:\PIO\Projects\Remote_AC_Controller'

Write-Host "=============================================="
Write-Host " PlatformIO Environment Preflight (READ-ONLY)"
Write-Host "=============================================="

# --------------------------------------------------------------------
# 1. pio --version  /  python --version
# --------------------------------------------------------------------
Write-Host "`n--- 1. Versions ---"
& $PIO --version 2>&1 | Write-Host
& $PY --version 2>&1 | Write-Host

# --------------------------------------------------------------------
# 2. pio system info
# --------------------------------------------------------------------
Write-Host "`n--- 2. pio system info ---"
& $PIO system info 2>&1 | ForEach-Object { Write-Host $_ }

# --------------------------------------------------------------------
# 3. pio settings get
# --------------------------------------------------------------------
Write-Host "`n--- 3. pio settings get ---"
$settingsRaw = & $PIO settings get 2>&1
$settingsRaw | ForEach-Object { Write-Host $_ }

# Parse persisted telemetry / cache from settings output - match "Current value" column
$settingsStr = $settingsRaw -join "`n"
$persistedTelemetryStr = if ($settingsStr -match 'enable_telemetry\s+(No|Yes)\s+\[') { $matches[1] } else { 'UNKNOWN' }
$persistedCacheStr     = if ($settingsStr -match 'enable_cache\s+(No|Yes)\s*(?:\s|$)')     { $matches[1] } else { 'UNKNOWN' }
$persistedTelemetry = ($persistedTelemetryStr -eq 'No')
$persistedCache     = ($persistedCacheStr -eq 'Yes')

# Read appstate.json for comparison
$appstate = $null
$appstateTelemetry = $null
$appstateCache = $null
$appstatePath = "$env:PLATFORMIO_CORE_DIR\appstate.json"
if (Test-Path $appstatePath) {
    try {
        $appstate = Get-Content $appstatePath -Raw | ConvertFrom-Json
        $appstateTelemetry = $appstate.settings.enable_telemetry
        $appstateCache     = $appstate.settings.enable_cache
    } catch { }
}

$processTelemetry = ($env:PLATFORMIO_SETTING_ENABLE_TELEMETRY -eq 'false')
$processCache     = ($env:PLATFORMIO_SETTING_ENABLE_CACHE -eq 'true')
$effectiveTelemetry = $processTelemetry  # env var overrides
$effectiveCache     = $processCache

Write-Host "`n--- Effective Settings ---"
Write-Host "PERSISTED_ENABLE_TELEMETRY=$persistedTelemetry (appstate=$appstateTelemetry)"
Write-Host "PROCESS_OVERRIDE_ENABLE_TELEMETRY=$processTelemetry"
Write-Host "EFFECTIVE_ENABLE_TELEMETRY=$effectiveTelemetry"
Write-Host "PERSISTED_ENABLE_CACHE=$persistedCache (appstate=$appstateCache)"
Write-Host "PROCESS_OVERRIDE_ENABLE_CACHE=$processCache"
Write-Host "EFFECTIVE_ENABLE_CACHE=$effectiveCache"

# --------------------------------------------------------------------
# 4. pio pkg list --global --verbose
# --------------------------------------------------------------------
Write-Host "`n--- 4. pio pkg list -g --verbose ---"
& $PIO pkg list -g --verbose 2>&1 | ForEach-Object { Write-Host $_ }

# --------------------------------------------------------------------
# 5. Per-env pio pkg list
# --------------------------------------------------------------------
$envs = @('nodemcuv2','nodemcuv2_probe','nodemcuv2_wifi_assoc',
          'nodemcuv2_portal_probe','nodemcuv2_campus_auth','nodemcuv2_srun_c_vector')
Write-Host "`n--- 5. Per-env pkg list ---"
foreach ($e in $envs) {
    Write-Host "`n>> ENV: $e"
    & $PIO pkg list --project-dir $ProjectDir -e $e --verbose 2>&1 | ForEach-Object { Write-Host $_ }
}

# --------------------------------------------------------------------
# 6. Platform package integrity check
# --------------------------------------------------------------------
Write-Host "`n--- 6. Platform package integrity ---"
$platformJson = Join-Path $env:PLATFORMIO_PLATFORMS_DIR 'espressif8266\platform.json'
if (-not (Test-Path $platformJson)) {
    Write-Host "FAIL: platform.json not found at $platformJson"
    Write-Host "LOCAL_PACKAGE_PREFLIGHT_PASS=False"
    exit 1
}

try {
    $plat = Get-Content $platformJson -Raw | ConvertFrom-Json
    $platVersion = $plat.version
    Write-Host "Platform: espressif8266 @ $platVersion"
    Write-Host "Required version: 4.2.1"
    $versionOk = ($platVersion -eq '4.2.1')
    Write-Host "VERSION_MATCH: $versionOk"

    $allPkgsOk = $true
    $pkgResults = @()

    if ($plat.packages) {
        foreach ($pkgName in $plat.packages.PSObject.Properties.Name) {
            $pkgSpec = $plat.packages.$pkgName
            $pkgVersion = if ($pkgSpec -is [string]) { $pkgSpec } else { $pkgSpec.version }
            $pkgDir = Join-Path $env:PLATFORMIO_PACKAGES_DIR $pkgName
            $pkgJson = Join-Path $pkgDir 'package.json'
            $pkgPiopm = Join-Path $pkgDir '.piopm'

            $exists = Test-Path $pkgDir
            $jsonOk = Test-Path $pkgJson
            $piopmOk = Test-Path $pkgPiopm
            $installedVersion = ''
            if ($jsonOk) {
                try { $pj = Get-Content $pkgJson -Raw | ConvertFrom-Json; $installedVersion = $pj.version } catch {}
            }

            $sha = ''
            if ($exists) {
                try { $sha = (Get-FileHash -Algorithm SHA256 -Path $pkgJson).Hash } catch {}
            }

            $exeOk = $false
            $exePath = ''
            if ($pkgName -eq 'toolchain-xtensa') {
                $exePath = Join-Path $pkgDir 'bin\xtensa-lx106-elf-gcc'
                $exeOk = Test-Path $exePath
            }

            $status = if ($exists -and $jsonOk -and $piopmOk) { 'OK' } else { 'INCOMPLETE' }
            if (-not $status -eq 'OK') { $allPkgsOk = $false }

            $pkgResults += [PSCustomObject]@{
                Name = $pkgName
                Required = $pkgVersion
                Installed = $installedVersion
                DirExists = $exists
                PkgJsonOk = $jsonOk
                PiopmOk = $piopmOk
                ExeOk = $exeOk
                SHA256 = if ($sha.Length -ge 16) { $sha.Substring(0,16) } else { $sha }
                Status = $status
            }
        }
    }

    Write-Host "`nPackage Integrity Report:"
    $pkgResults | Format-Table -AutoSize | Out-String | Write-Host

    $preflightPass = $allPkgsOk -and $versionOk
    Write-Host "LOCAL_PACKAGE_PREFLIGHT_PASS=$preflightPass"

} catch {
    Write-Host "FAIL: Could not parse platform.json: $_"
    Write-Host "LOCAL_PACKAGE_PREFLIGHT_PASS=False"
    exit 1
}

# --------------------------------------------------------------------
# 7. Check for mixed Core directories
# --------------------------------------------------------------------
Write-Host "`n--- 7. Mixed Core detection ---"
$otherPios = @()
Get-Command pio -ErrorAction SilentlyContinue | ForEach-Object { $otherPios += $_.Source }
Get-Command platformio -ErrorAction SilentlyContinue | ForEach-Object { $otherPios += $_.Source }
Write-Host "other-pio-on-PATH:" 
$otherPios | ForEach-Object { Write-Host "  $_" }

Write-Host "`n=============================================="
Write-Host " PREFLIGHT COMPLETE"
Write-Host " LOCAL_PACKAGE_PREFLIGHT_PASS=$preflightPass"
Write-Host " EFFECTIVE_ENABLE_TELEMETRY=$effectiveTelemetry"
Write-Host " EFFECTIVE_ENABLE_CACHE=$effectiveCache"
Write-Host "=============================================="
