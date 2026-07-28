# make_review_package.ps1
# Generates the ESP8266 PlatformIO environment review ZIP package (v1.1).
#
# Hardened per the third-party review (Sections 6/7/8):
#   6. Verification is strict; any failure -> exit 1, temp verify dir kept.
#   7. Sensitive scan is per-file (SAFE_PLACEHOLDER / SUSPECT_SECRET) and blocks
#      packaging on real secrets.
#   8. Excludes caches/__pycache__/*.pyc/*.bak and de-dupes logs; ZIP uses
#      forward-slash entry names (Windows + Linux, no warnings).
#
# Staging layout:
#   project/  -> source only (excl .platformio/.pio/.git/.workbuddy/secrets.h/
#               __pycache__/*.pyc/*.bak and the internal logs/ folder)
#   review/   -> env_info.txt, MANIFEST.csv, SENSITIVE_SCAN.txt, evidence/*,
#               known-issues.md, review-summary.md
#   logs/     -> actual run logs copied from $proj/logs
#
# Exit codes:
#   0  = all checks passed, package created and verified
#   1  = verification / scan / required-file failure (verify dir preserved)
#   2  = pio core missing
param()

$ErrorActionPreference = 'Continue'
$proj    = "F:\PIO\Projects\Remote_AC_Controller"
$newCore = "F:\PIO\Core"
$env:PLATFORMIO_CORE_DIR = $newCore
$env:NO_PROXY = (($env:NO_PROXY -split ',') + '.platformio.org','platformio.org','.espressif.com','espressif.com','github.com','.github.com' | Sort-Object -Unique) -join ','

$pio    = Join-Path $newCore 'penv\Scripts\pio.exe'
$py     = Join-Path $newCore 'penv\Scripts\python.exe'
if (-not (Test-Path $pio))    { Write-Error "pio not found at $pio"; exit 2 }
if (-not (Test-Path $py))     { Write-Error "python not found at $py"; exit 2 }

$parent  = "F:\PIO"
$ts      = Get-Date -Format 'yyyyMMdd_HHmmss'
$zipName = "ESP8266_PlatformIO_Environment_Review_Package_v1.1_$ts.zip"
$zipPath = Join-Path $parent $zipName
$stage   = Join-Path $env:TEMP ("review_stage_$ts")
$verify  = Join-Path $env:TEMP ("review_verify_$ts")
$verifyReport = Join-Path $parent ($zipName + '.verify.txt')
if (Test-Path $stage)  { Remove-Item $stage  -Recurse -Force }
if (Test-Path $verify) { Remove-Item $verify -Recurse -Force }
if (Test-Path $verifyReport) { Remove-Item $verifyReport -Force }

$projDir = Join-Path $stage 'project'
$revDir  = Join-Path $stage 'review'
$logDir  = Join-Path $stage 'logs'
New-Item -ItemType Directory -Force -Path $projDir, $revDir, $logDir | Out-Null

function Fail($msg) {
    Write-Error $msg
    Write-Output "PACKAGE_RESULT=FAILED"
    Write-Output "FAIL_REASON=$msg"
    Write-Output "VERIFY_DIR_PRESERVED=$verify"
    Write-Output "STAGE_DIR_PRESERVED=$stage"
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Copy SOURCE only (exclude heavy / secret / cache dirs and binaries)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 2. Copy ACTUAL run logs from $proj/logs (root-level logs/ only)
# ---------------------------------------------------------------------------
$srcLogs = Join-Path $proj 'logs'
if (Test-Path $srcLogs) {
    Get-ChildItem $srcLogs -File | ForEach-Object { Copy-Item $_.FullName (Join-Path $logDir $_.Name) -Force }
}

# 2b. Evidence CSV + firmware.bin SHA256
$evDir = Join-Path $revDir 'evidence'
New-Item -ItemType Directory -Force -Path $evDir | Out-Null
$dlEvidence = "F:\PIO\Downloads\download_evidence.csv"
if (Test-Path $dlEvidence) { Copy-Item $dlEvidence (Join-Path $evDir 'download_evidence.csv') -Force }
else { Fail "download_evidence.csv missing at $dlEvidence (Section 5)" }
$fw = Join-Path $proj '.pio\build\nodemcuv2\firmware.bin'
if (Test-Path $fw) {
    $fh = (Get-FileHash -Algorithm SHA256 $fw).Hash
    "firmware.bin_sha256=$fh" | Out-File (Join-Path $revDir 'firmware_bin_sha256.txt') -Encoding utf8
}

# Copy review docs (known-issues, review-summary) into review/
foreach ($doc in @('known-issues.md', 'review-summary.md')) {
    $src = Join-Path (Join-Path $proj 'review') $doc
    if (Test-Path $src) { Copy-Item $src (Join-Path $revDir $doc) -Force }
}

# ---------------------------------------------------------------------------
# 3. Environment info (copied from the freshly-generated review/env_info.txt;
#    if absent, fall back to a basic capture using the new Core).
# ---------------------------------------------------------------------------
$envInfo = Join-Path $revDir 'env_info.txt'
$srcEnv  = Join-Path (Join-Path $proj 'review') 'env_info.txt'
if (Test-Path $srcEnv) {
    Copy-Item $srcEnv $envInfo -Force
} else {
    & $pio --version 2>&1 | Out-File $envInfo -Encoding utf8
    '' | Out-File $envInfo -Append -Encoding utf8
    '=== where.exe pio ===' | Out-File $envInfo -Append -Encoding utf8
    where.exe pio 2>&1 | Out-File $envInfo -Append -Encoding utf8
    '' | Out-File $envInfo -Append -Encoding utf8
    '=== pio system info ===' | Out-File $envInfo -Append -Encoding utf8
    & $pio system info 2>&1 | Out-File $envInfo -Append -Encoding utf8
    '' | Out-File $envInfo -Append -Encoding utf8
    '=== PLATFORMIO_CORE_DIR ===' | Out-File $envInfo -Append -Encoding utf8
    $env:PLATFORMIO_CORE_DIR | Out-File $envInfo -Append -Encoding utf8
}

# ---------------------------------------------------------------------------
# 4. Sensitive-information scan (per-file; blocks packaging on SUSPECT)
# ---------------------------------------------------------------------------
$scan = Join-Path $revDir 'SENSITIVE_SCAN.txt'
$scanCode = & $py 'F:\PIO\Projects\Remote_AC_Controller\tools\scan_secrets.py' $proj $scan 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Output ($scanCode | Out-String)
    Fail "Sensitive scan reported SUSPECT secrets (see review/SENSITIVE_SCAN.txt); packaging blocked"
}

# ---------------------------------------------------------------------------
# 5. Manifest (forward-slash relative paths; MANIFEST.csv not self-listed)
# ---------------------------------------------------------------------------
$manifest = Join-Path $revDir 'MANIFEST.csv'
'relative_path,size_bytes,sha256' | Out-File $manifest -Encoding utf8
$seenPaths = @{}
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    if ($_.FullName -eq $manifest) { return }
    $rel  = $_.FullName.Substring($stage.Length).TrimStart('\').Replace('\', '/')
    if ($seenPaths.ContainsKey($rel)) { Fail "Duplicate manifest path: $rel" }
    $seenPaths[$rel] = $true
    $hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash
    "$rel,$($_.Length),$hash" | Out-File $manifest -Append -Encoding utf8
}

# ---------------------------------------------------------------------------
# 6. Compress with forward-slash entry names
# ---------------------------------------------------------------------------
& $py 'F:\PIO\Projects\Remote_AC_Controller\tools\build_zip.py' $stage $zipPath 2>&1 | Out-String -Width 200 | Write-Output
if (-not (Test-Path $zipPath)) { Fail "ZIP was not created" }
$zipSize = (Get-Item $zipPath).Length
if ($zipSize -eq 0) { Fail "ZIP is empty (0 bytes)" }

# ---------------------------------------------------------------------------
# 7. Verify: extract, re-check size + SHA256, no missing/extra/duplicate
# ---------------------------------------------------------------------------
Expand-Archive -Path $zipPath -DestinationPath $verify -Force
$extractedFiles = Get-ChildItem $verify -Recurse -File
$extractedCount = $extractedFiles.Count
$manifestEntries = (Get-Content $manifest | Where-Object { $_ -and $_ -ne 'relative_path,size_bytes,sha256' }).Count
$matchAll = $true
$mismatches = @()
$missingFromManifest = @()
$manifestRelSet = @{}
foreach ($line in (Get-Content $manifest | Where-Object { $_ -and $_ -ne 'relative_path,size_bytes,sha256' })) {
    $parts = $line -split ','
    $manifestRelSet[$parts[0]] = @{ size = [int]$parts[1]; sha = $parts[2] }
}
# Check each extracted content file against the manifest
foreach ($f in $extractedFiles) {
    $rel = $f.FullName.Substring($verify.Length).TrimStart('\').Replace('\', '/')
    if ($rel -eq 'review/MANIFEST.csv') { continue }   # the index itself
    if (-not $manifestRelSet.ContainsKey($rel)) {
        $missingFromManifest += $rel; $matchAll = $false; continue
    }
    $exp = $manifestRelSet[$rel]
    if ($f.Length -ne $exp.size) {
        $mismatches += "$rel (size $($f.Length) != $($exp.size))"; $matchAll = $false
    }
    $h = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash
    if ($h -ne $exp.sha) {
        $mismatches += "$rel (sha256 mismatch)"; $matchAll = $false
    }
    $manifestRelSet.Remove($rel)
}
# Any manifest entries left were not found in the extract
foreach ($k in $manifestRelSet.Keys) {
    $mismatches += "$k (listed in manifest but missing from archive)"; $matchAll = $false
}

# Required files present (forward-slash)
$required = @(
    'review/env_info.txt', 'review/MANIFEST.csv', 'review/SENSITIVE_SCAN.txt',
    'review/known-issues.md', 'review/review-summary.md', 'review/evidence/download_evidence.csv',
    'project/setup-report.md',
    'project/tools/download_verify.py', 'project/tools/test_integrity.py',
    'project/tools/smoke_test.ps1', 'project/tools/detect_port.ps1',
    'project/tools/build.ps1', 'project/tools/upload.ps1', 'project/tools/monitor.ps1',
    'project/tools/make_review_package.ps1', 'project/tools/scan_secrets.py', 'project/tools/build_zip.py'
)
$missingRequired = @()
foreach ($r in $required) {
    if (-not (Test-Path (Join-Path $verify $r.Replace('/', '\')))) { $missingRequired += $r }
}
if ($missingRequired.Count -gt 0) { $matchAll = $false }

$zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash

# Re-read scan result for the report
$scanTail = (Get-Content $scan | Where-Object { $_ -like 'RESULT:*' })
"=== VERIFICATION ==="                                        | Out-File $verifyReport -Encoding utf8
"zip_path=$zipPath"                                           | Out-File $verifyReport -Append -Encoding utf8
"zip_size_bytes=$zipSize"                                     | Out-File $verifyReport -Append -Encoding utf8
"zip_sha256=$zipHash"                                         | Out-File $verifyReport -Append -Encoding utf8
"extracted_file_count=$extractedCount"                        | Out-File $verifyReport -Append -Encoding utf8
"manifest_entry_count=$manifestEntries"                       | Out-File $verifyReport -Append -Encoding utf8
"extracted_vs_manifest=manifest_entry_count+1 (index)"        | Out-File $verifyReport -Append -Encoding utf8
"sha256_all_match=$matchAll"                                  | Out-File $verifyReport -Append -Encoding utf8
"sha256_mismatches=$(($mismatches -join '; '))"                | Out-File $verifyReport -Append -Encoding utf8
"files_not_in_manifest=$(($missingFromManifest -join '; '))"  | Out-File $verifyReport -Append -Encoding utf8
"missing_required_files=$(($missingRequired -join '; '))"     | Out-File $verifyReport -Append -Encoding utf8
"scan_result=$scanTail"                                       | Out-File $verifyReport -Append -Encoding utf8

if (-not $matchAll) {
    Fail "Verification failed: mismatches=[$($mismatches -join '; ')] not_in_manifest=[$($missingFromManifest -join '; ')] missing_required=[$($missingRequired -join '; ')]"
}

# ---------------------------------------------------------------------------
# 8. Cleanup temp dirs ONLY on full success
# ---------------------------------------------------------------------------
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $verify -Recurse -Force -ErrorAction SilentlyContinue

Write-Output "REVIEW_PACKAGE=$zipPath"
Write-Output "SIZE_BYTES=$zipSize"
Write-Output "SHA256=$zipHash"
Write-Output "FILE_COUNT=$extractedCount"
Write-Output "MANIFEST_ENTRIES=$manifestEntries"
Write-Output "VERIFY_SHA256_MATCH=$matchAll"
Write-Output "VERIFY_REPORT=$verifyReport"
Write-Output "PACKAGE_RESULT=PASSED"
exit 0
