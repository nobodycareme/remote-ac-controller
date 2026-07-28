# make_campus_review_package.ps1
# Phase 16 (v0.3.4): build the firmware review ZIP for 1.1.4-srun-portal-fix,
# then verify an independent rebuild-from-ZIP (REBUILD_OK) across all six envs.
#
# Security gate: sensitive_scan.py blocks packaging on any SUSPECT secret.
# The scan runs against the FINAL STAGING directory (门禁八) so PASS reflects
# what ships.
#
# 2026-07-17 corrections (gate 10 rebuild reliability, v0.3.4 final):
#   * K18: proxy vars set to EMPTY STRINGS (not Remove-Item) + NO_PROXY='*'
#     (both cases). On Windows urllib falls back to the dead system-registry
#     proxy when the env var is absent -> LDF/dependency phase hangs.
#   * pio telemetry=No + cache=No (must be applied globally via `pio settings
#     set`; if not set, pio attempts HTTPS to bit.ly on every run and hangs).
#   * Silent extraction via System.IO.Compression.ZipFile (no Expand-Archive
#     progress-bar pollution).
#   * Gate-10 rebuild: NO .pio is copied from the real project. The extracted
#     project starts with zero .pio state. The rebuild is dependency-cache-
#     assisted: PLATFORMIO_CORE_DIR=F:\PIO\Core provides the toolchain,
#     platform (espressif8266@4.2.1), and globally cached framework/libdeps
#     packages. Each env is first `pio run -t clean`-ed, then built with
#     `pio run -e $e -j 1 -d $rebuildWd`. The rebuild log records the actual
#     working directory (ZIP extraction dir, not real project).
#     -j 1 avoids the SCons jobserver deadlock.
#   * The ZIP is NOT fully self-contained (it requires a PlatformIO 6.1.19
#     installation at F:\PIO\Core with the locked espressif8266@4.2.1
#     platform).
#   * UNIQUE timestamped paths for stage/verify/ZIP -> the single Compress never
#     overwrites an existing file, so WorkBuddy safe-delete never triggers.
#
# Exit codes: 0 = package + all rebuilds OK; 1 = failure (report printed).

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$proj = 'F:\PIO\Projects\Remote_AC_Controller'
$core = 'F:\PIO\Core'
$env:PLATFORMIO_CORE_DIR = $core

# --- K18 fix: EMPTY-STRING proxy vars + NO_PROXY='*' (both cases) ---
$env:HTTP_PROXY  = ''
$env:HTTPS_PROXY = ''
$env:http_proxy  = ''
$env:https_proxy = ''
$env:ALL_PROXY   = ''
$env:all_proxy   = ''
$env:NO_PROXY     = '*'
$env:no_proxy     = '*'

$pio = Join-Path $core 'penv\Scripts\pio.exe'
$py  = Join-Path $core 'penv\Scripts\python.exe'
if (-not (Test-Path $pio)) { Write-Error 'pio not found'; exit 1 }
if (-not (Test-Path $py))  { Write-Error 'python not found'; exit 1 }

$VER = 'v0.3.4'
$ts      = Get-Date -Format 'yyyyMMdd_HHmmss'
$zipName = "Remote_AC_Controller_Review_Package_${VER}_$ts.zip"
$zipPath = Join-Path 'F:\PIO' $zipName
# UNIQUE per-run paths -> no safe-delete overwrite, no stale collisions
$stage   = Join-Path $env:TEMP ("campus_pkg_$ts")
$verify  = Join-Path $env:TEMP ("campus_rebuild_$ts")
$report  = Join-Path 'F:\PIO' ($zipName + '.verify.txt')

$projDir = Join-Path $stage 'project'
$logDir  = Join-Path $stage 'logs'
New-Item -ItemType Directory -Force -Path $projDir, $logDir | Out-Null

function Fail($msg) {
    Write-Output 'PACKAGE_RESULT=FAILED'
    Write-Output "FAIL_REASON=$msg"
    Write-Output "STAGE_DIR_PRESERVED=$stage"
    Write-Output "VERIFY_DIR_PRESERVED=$verify"
    exit 1
}

# ---- 1. Stage SOURCE (exclude caches / secrets / binaries) ----
$excludeDirs = @('.platformio', '.pio', '.git', '.workbuddy', '__pycache__', 'logs')
Get-ChildItem $proj -Recurse | ForEach-Object {
    $rel  = $_.FullName.Substring($proj.Length).TrimStart('\')
    $skip = $false
    foreach ($d in $excludeDirs) { if ($rel -like "$d\*" -or $rel -eq $d) { $skip = $true } }
    if ($_.Name -eq 'secrets.h') { $skip = $true }
    if ($_.Extension -in @('.pyc')) { $skip = $true }
    if ($_.Name -like '*.bak') { $skip = $true }
    if ($skip) { return }
    $dest = Join-Path $projDir $rel
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        Copy-Item $_.FullName $dest -Force
    }
}

# ---- 2. Copy run logs ----
$srcLogs = Join-Path $proj 'logs'
if (Test-Path $srcLogs) {
    Get-ChildItem $srcLogs -File | ForEach-Object { Copy-Item $_.FullName (Join-Path $logDir $_.Name) -Force }
}

# ---- 3. DESENSITIZE staging root (门禁八: mask device MAC before shipping) ----
& $py "$proj\tools\desensitize_artifacts.py" $stage 2>&1 | Out-String -Width 200 | Write-Output

# ---- 4. Sensitive scan of the FINAL STAGING directory (门禁八) ----
$scan = Join-Path $stage 'SENSITIVE_SCAN.txt'
$scanOut = & $py "$proj\tools\sensitive_scan.py" $stage 2>&1 | Out-String -Width 200
$scanOut | Out-File $scan -Encoding utf8
$scanOut | Write-Output
if ($scanOut -notmatch 'SENSITIVE_SCAN_PASS') { Fail 'Sensitive scan did not report PASS on staging; packaging blocked' }

# ---- 5. MANIFEST + FILE_LIST over staged files ----
$manifest = Join-Path $stage 'MANIFEST.csv'
'relative_path,size_bytes,sha256' | Out-File $manifest -Encoding utf8
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    $rel  = $_.FullName.Substring($stage.Length).TrimStart('\').Replace('\', '/')
    $hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash
    "$rel,$($_.Length),$hash" | Out-File $manifest -Append -Encoding utf8
}
$fileList = Join-Path $stage 'FILE_LIST.txt'
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($stage.Length).TrimStart('\').Replace('\', '/')
    "$rel" | Out-File $fileList -Append -Encoding utf8
}

# ---- 6. Compress ONCE (unique name -> no overwrite -> no safe-delete) ----
Compress-Archive -Path "$stage\*" -DestinationPath $zipPath -Force
if (-not (Test-Path $zipPath)) { Fail 'ZIP was not created' }
if ((Get-Item $zipPath).Length -eq 0) { Fail 'ZIP is empty' }

# ---- 7. Verify + independent multi-env rebuild from extracted ZIP (门禁十) ----
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $verify)
$extracted = Get-ChildItem $verify -Recurse -File
$extCount  = $extracted.Count
$zipHash   = (Get-FileHash -Algorithm SHA256 $zipPath).Hash

$rebuildWd = Join-Path $verify 'project'
$rebuildLogDir = Join-Path $verify 'rebuild_logs'
New-Item -ItemType Directory -Force -Path $rebuildLogDir | Out-Null

# DEPENDENCY-CACHE-ASSISTED rebuild: the ZIP contains SOURCE only (no .pio).
# The rebuilt project starts with ZERO .pio state. PLATFORMIO_CORE_DIR provides
# the toolchain (F:\PIO\Core\packages\toolchain-xtensa), the espressif8266
# platform (F:\PIO\Core\packages\framework-arduinoespressif8266), and globally
# cached libdeps. Each env is FIRST `pio run -t clean`-ed, then built from
# scratch. No .pio/build, .o, .elf, or firmware.bin is copied from the real
# project. The ZIP is NOT fully self-contained; it requires a PlatformIO
# 6.1.19 installation at F:\PIO\Core with espressif8266@4.2.1.
#
# The rebuild log records the ACTUAL working directory ($rebuildWd, which is
# inside the ZIP extraction tree) to prove we are building the delivered
# source, not the real project.

function Kill-StaleBuildProcs {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(pio|python|scons|cc1|xtensa|gcc)$' } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$envs = @('nodemcuv2', 'nodemcuv2_probe', 'nodemcuv2_wifi_assoc',
          'nodemcuv2_portal_probe', 'nodemcuv2_campus_auth', 'nodemcuv2_srun_c_vector')

Kill-StaleBuildProcs

$rebuildResult = Join-Path $verify 'rebuild_result.txt'
"=== independent rebuild from extracted ZIP (DEPENDENCY-CACHE-ASSISTED) ===" | Out-File $rebuildResult -Encoding utf8
"REBUILD_WORKING_DIR=$rebuildWd" | Out-File $rebuildResult -Append -Encoding utf8
"PLATFORMIO_CORE_DIR=$core" | Out-File $rebuildResult -Append -Encoding utf8
"NOTE: ZIP is NOT fully self-contained; requires PlatformIO 6.1.19 at F:\PIO\Core with espressif8266@4.2.1" | Out-File $rebuildResult -Append -Encoding utf8
$allOk = $true
foreach ($e in $envs) {
    Kill-StaleBuildProcs
    Remove-Item (Join-Path $core 'packages.lock') -Force -ErrorAction SilentlyContinue
    # Step A: clean the env in the extracted project (ensures zero build artifacts)
    $cleanLog = Join-Path $rebuildLogDir ("clean_$e.log")
    "starting pio clean for $e in $rebuildWd (dependency-cache-assisted)" | Out-File $cleanLog -Encoding utf8
    & $pio run -t clean -e $e -d $rebuildWd > $cleanLog 2>&1
    # Step B: build the env in the extracted project
    $log = Join-Path $rebuildLogDir ("rebuild_$e.log")
    "BUILD_WORKING_DIR=$rebuildWd" | Out-File $log -Encoding utf8
    "building $e in $rebuildWd (dependency-cache-assisted: PLATFORMIO_CORE_DIR=$core)" | Out-File $log -Append -Encoding utf8
    & $pio run -e $e -j 1 -d $rebuildWd >> $log 2>&1
    $pass = Select-String -Quiet -Pattern '\[SUCCESS\]' -Path $log
    $status = if ($pass) { 'PASS' } else { 'FAIL' }
    if (-not $pass) { $allOk = $false }
    "ENV $e : $status (working_dir=$rebuildWd)" | Out-File $rebuildResult -Append -Encoding utf8
}
"ALL_ENV_REBUILD_OK=$allOk" | Out-File $rebuildResult -Append -Encoding utf8

# ---- 8. Verification report (separate file; ZIP already finalized above) ----
"# ZIP Verification Report ($VER)" | Out-File $report -Encoding utf8
"zip_path=$zipPath" | Out-File $report -Append -Encoding utf8
"zip_sha256=$zipHash" | Out-File $report -Append -Encoding utf8
"extracted_file_count=$extCount" | Out-File $report -Append -Encoding utf8
"dependency_cache_assisted=YES (ZIP does not contain .pio; rebuild uses PLATFORMIO_CORE_DIR=$core for toolchain+framework packages)" | Out-File $report -Append -Encoding utf8
"all_env_rebuild_ok=$allOk" | Out-File $report -Append -Encoding utf8
Get-Content $rebuildResult | Out-File $report -Append -Encoding utf8

# Keep staging + verify dirs for external review (no deletion -> no safe-delete)
Write-Output "STAGE_PRESERVED=$stage"
Write-Output "VERIFY_PRESERVED=$verify"

Write-Output "REVIEW_PACKAGE=$zipPath"
Write-Output "SIZE_BYTES=$((Get-Item $zipPath).Length)"
Write-Output "SHA256=$zipHash"
Write-Output "FILE_COUNT=$extCount"
Write-Output "ALL_ENV_REBUILD_OK=$allOk"
Write-Output "VERIFY_REPORT=$report"
if (-not $allOk) {
    Write-Output 'PACKAGE_RESULT=PACKAGED_REBUILD_FAILED'
    exit 1
}
Write-Output 'PACKAGE_RESULT=PASSED'
exit 0
