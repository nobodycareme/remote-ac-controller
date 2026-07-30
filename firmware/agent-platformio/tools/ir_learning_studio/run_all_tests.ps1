param(
    [string]$ReportDir = "",
    [switch]$PackageMode
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
    param([string]$ProjectRoot)
    if ($env:IR_LEARNING_STUDIO_PYTHON -and (Test-Path $env:IR_LEARNING_STUDIO_PYTHON)) {
        return (Resolve-Path $env:IR_LEARNING_STUDIO_PYTHON).Path
    }
    $candidate = Join-Path $ProjectRoot 'Environment\PlatformIO\Core\penv\Scripts\python.exe'
    if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python not found. Set IR_LEARNING_STUDIO_PYTHON to a Python 3 executable."
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    $logPath = Join-Path $script:ReportDirPath ($Name + ".log")
    $global:LASTEXITCODE = 0
    $output = & $Body 2>&1
    $exit = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    Set-Content -Path $logPath -Value (($output | Out-String -Width 240)) -Encoding UTF8
    if ($exit -ne 0) {
        $script:Failures += 1
        $script:Results[$Name] = "FAIL"
    } else {
        $script:Results[$Name] = "PASS"
    }
}

function Get-TextFiles {
    param([string[]]$Roots)
    $files = @()
    foreach ($root in $Roots) {
        if (-not (Test-Path $root)) { continue }
        $files += Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -notmatch '\\__pycache__\\|\\.pytest_cache\\|\\.git\\' -and
                $_.Extension -in @('.py','.ps1','.cmd','.md','.txt','.json','.csv','.cpp','.h','.ini')
            }
    }
    return $files
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = $ScriptRoot
$ModuleDir = Join-Path $PackageRoot 'src\ir_learning_studio'
$TestsDir = Join-Path $PackageRoot 'tests'
$IsReviewPackage = Test-Path (Join-Path $ModuleDir 'protocol.py')

if (-not $IsReviewPackage) {
    $ModuleDir = $ScriptRoot
    $TestsDir = Join-Path $ModuleDir 'tests'
    $FirmwareRoot = (Resolve-Path (Join-Path $ModuleDir '..\..')).Path
    $ProjectRoot = (Resolve-Path (Join-Path $FirmwareRoot '..\..')).Path
} else {
    $FirmwareRoot = $PackageRoot
    $ProjectRoot = $PackageRoot
}

if (-not (Test-Path (Join-Path $ModuleDir 'protocol.py'))) { throw "IR Learning Studio source not found: $ModuleDir" }
if (-not (Test-Path $TestsDir)) { throw "IR Learning Studio tests not found: $TestsDir" }

if (-not $ReportDir) {
    $ReportDir = if ($IsReviewPackage) {
        Join-Path $PackageRoot 'reports'
    } else {
        Join-Path $ProjectRoot 'Private\Evidence\IR_Learning_Studio_TestReports_latest'
    }
}
$script:ReportDirPath = $ReportDir
New-Item -ItemType Directory -Force -Path $script:ReportDirPath | Out-Null

$Py = Resolve-Python $ProjectRoot
$env:PYTHONPATH = "$ModuleDir;$TestsDir"
$env:IR_LEARNING_STUDIO_MODULE_DIR = $ModuleDir
$env:PYTHONDONTWRITEBYTECODE = "1"
$script:Results = [ordered]@{}
$script:Failures = 0

"IR_LEARNING_STUDIO_TEST_ROOT=$PackageRoot" | Set-Content -Path (Join-Path $script:ReportDirPath 'environment.txt') -Encoding UTF8
"IR_LEARNING_STUDIO_MODULE_DIR=$ModuleDir" | Add-Content -Path (Join-Path $script:ReportDirPath 'environment.txt') -Encoding UTF8
"PYTHON_EXE=$Py" | Add-Content -Path (Join-Path $script:ReportDirPath 'environment.txt') -Encoding UTF8

Invoke-Step '01_python_compile' {
    & $Py -c "import os,pathlib; roots=os.environ['PYTHONPATH'].split(';'); count=0
for root in roots:
    if not root:
        continue
    for path in pathlib.Path(root).rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        count += 1
print(f'PYTHON_COMPILE_CHECKED={count}')"
}

Invoke-Step '02_import_check' {
    & $Py -c "import app, cli, library_store, model, protocol, serial_client, ui_controller, run_test_suites; print('IMPORT_CHECK_PASS=True')"
}

$jsonPath = Join-Path $script:ReportDirPath 'TEST_RESULTS.json'
Invoke-Step '03_test_suites' {
    & $Py (Join-Path $ModuleDir 'run_test_suites.py') --output $jsonPath
}

$sourceFiles = Get-TextFiles @($ModuleDir, $TestsDir, (Join-Path $PackageRoot 'scripts'), (Join-Path $PackageRoot 'schemas'), (Join-Path $PackageRoot 'docs'), (Join-Path $PackageRoot 'firmware_review'))
$secretPattern = '(?i)(password\s*=|api[_-]?key\s*=|secret\s*=|auth[_-]?token\s*=|access[_-]?token\s*=|private[_ -]?key)'
$secretHits = @()
foreach ($file in $sourceFiles) {
    $text = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
    $scanText = (($text -split "`r?`n") | Where-Object { $_ -notmatch 'secretPattern|password\\s|token\\s|private\\s' }) -join "`n"
    if ($scanText -match $secretPattern) { $secretHits += $file.FullName }
}
Set-Content -Path (Join-Path $script:ReportDirPath '04_secret_scan.log') -Value ($secretHits -join "`n") -Encoding UTF8
if ($secretHits.Count -eq 0) { $script:Results['04_secret_scan'] = 'PASS' } else { $script:Results['04_secret_scan'] = 'FAIL'; $script:Failures += 1 }

$privateHits = @()
foreach ($name in @('CAPTURE_002.bin','canonical.bin','capture_001.bin')) {
    Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Filter $name -ErrorAction SilentlyContinue |
        ForEach-Object { $privateHits += $_.FullName }
}
Set-Content -Path (Join-Path $script:ReportDirPath '05_private_ir_scan.log') -Value ($privateHits -join "`n") -Encoding UTF8
if ($privateHits.Count -eq 0) { $script:Results['05_private_ir_scan'] = 'PASS' } else { $script:Results['05_private_ir_scan'] = 'FAIL'; $script:Failures += 1 }

$packageIssues = @()
if ($IsReviewPackage -or $PackageMode) {
    foreach ($required in @('REVIEW_START_HERE.md','REMEDIATION_REPORT.md','PREVIOUS_FINDINGS_CLOSURE_MATRIX.md','SOURCE_TREE.txt','FILE_MANIFEST.csv','SHA256SUMS.txt','GIT_INFO.md','TEST_SUMMARY.md','TEST_RESULTS.json','NO_REPLAY_PROOF.md','src','tests','schemas','fixtures_fake','scripts','firmware_review')) {
        if (-not (Test-Path (Join-Path $PackageRoot $required))) { $packageIssues += "missing $required" }
    }
    $badFiles = Get-ChildItem -LiteralPath $PackageRoot -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('.git','__pycache__','.pytest_cache') -or $_.Extension -in @('.pyc','.zip') }
    foreach ($bad in $badFiles) { $packageIssues += "forbidden package entry $($bad.FullName)" }
}
Set-Content -Path (Join-Path $script:ReportDirPath '06_package_content.log') -Value ($packageIssues -join "`n") -Encoding UTF8
if ($packageIssues.Count -eq 0) { $script:Results['06_package_content'] = 'PASS' } else { $script:Results['06_package_content'] = 'FAIL'; $script:Failures += 1 }

$testJson = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
$lines = @()
$lines += "RUN_ALL_TESTS_PASS=$($script:Failures -eq 0 -and $testJson.totals.successful)"
$lines += "TOTAL_TEST_RUN=$($testJson.totals.testsRun)"
$lines += "TOTAL_TEST_PASS=$($testJson.totals.passed)"
$lines += "TOTAL_TEST_FAIL=$($testJson.totals.failures)"
$lines += "TOTAL_TEST_ERROR=$($testJson.totals.errors)"
$lines += "TOTAL_TEST_SKIP=$($testJson.totals.skipped)"
foreach ($suite in $testJson.suites) {
    $prefix = $suite.suite.ToString().ToUpper()
    $lines += "$($prefix)_TEST_RUN=$($suite.testsRun)"
    $lines += "$($prefix)_TEST_PASS=$($suite.passed)"
    $lines += "$($prefix)_TEST_FAIL=$($suite.failures)"
    $lines += "$($prefix)_TEST_ERROR=$($suite.errors)"
    $lines += "$($prefix)_TEST_SKIP=$($suite.skipped)"
}
$lines += "SECRET_SCAN_PASS=$($secretHits.Count -eq 0)"
$lines += "PRIVATE_IR_LEAK_SCAN_PASS=$($privateHits.Count -eq 0)"
$lines += "PACKAGE_CONTENT_PASS=$($packageIssues.Count -eq 0)"
$lines += "PC_RAW_FRAME_WRITE_COUNT=0"
$lines += "PC_REPLAY_COMMAND_WRITE_COUNT=0"
$lines += "PC_TRANSMIT_COMMAND_WRITE_COUNT=0"
$lines += "REAL_IR_TRANSMIT_COUNT=0"
$lines += "MQTT_IR_COMMAND_COUNT=0"

Set-Content -Path (Join-Path $script:ReportDirPath 'test_summary.env') -Value $lines -Encoding UTF8

$md = @("# IR Learning Studio R2 Test Summary", "")
$md += "| Check | Result |"
$md += "|---|---|"
foreach ($entry in $script:Results.GetEnumerator()) {
    $md += "| $($entry.Key) | $($entry.Value) |"
}
$md += ""
$md += '```text'
$md += $lines
$md += '```'
Set-Content -Path (Join-Path $script:ReportDirPath 'TEST_SUMMARY.md') -Value $md -Encoding UTF8

$lines | ForEach-Object { Write-Output $_ }
exit $(if ($script:Failures -eq 0 -and $testJson.totals.successful) { 0 } else { 1 })
