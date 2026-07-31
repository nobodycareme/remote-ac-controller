# tools/dev_ps1_tooling_tests.ps1
#
# Tooling regression test for dev.ps1 Invoke-Pio.
#
# Verifies that the native process exit code is propagated as a SINGLE,
# strongly-typed result object, and that native stdout/stderr do NOT pollute
# the return value (which previously produced an Object[] and a false-negative
# `-ne 0` comparison).
#
# Uses fake native commands only. Does NOT require a real PlatformIO install,
# does NOT build firmware, and does NOT modify dev.ps1.
#
# Exit code: 0 when all four scenarios pass, 1 otherwise.

$ErrorActionPreference = 'Continue'

$here   = $PSScriptRoot
$DevPs1 = Join-Path $here 'dev.ps1'

$tmp = Join-Path $env:TEMP 'dev_ps1_tooling_tests'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

function New-FakePio($name, $body) {
    $p = Join-Path $tmp $name
    Set-Content -Path $p -Value $body -Encoding ASCII
    return $p
}

# Scenario A: native stdout + exit 0  -> PASS
$fakeA = New-FakePio 'fake_a.bat' "@echo off`r`necho STDOUT_CONTENT`r`nexit /b 0`r`n"
# Scenario B: native stderr warning + exit 0 -> PASS
$fakeB = New-FakePio 'fake_b.bat' "@echo off`r`necho STDERR_WARNING 1>&2`r`nexit /b 0`r`n"
# Scenario C: native stderr error + exit 7 -> FAIL (ExitCode must be 7)
$fakeC = New-FakePio 'fake_c.bat' "@echo off`r`necho STDERR_ERROR 1>&2`r`nexit /b 7`r`n"
# Scenario D: large stdout/stderr burst + exit 0 -> still a single result object
$sb = New-Object System.Text.StringBuilder
$sb.AppendLine('@echo off') | Out-Null
for ($i = 1; $i -le 500; $i++) { $sb.AppendLine("echo LINE_$i") | Out-Null }
# No caret-escaping here: the line is written verbatim into the .bat file, it is
# not typed at a cmd prompt. `1^>^&2` would emit the redirection as literal text
# and the scenario would never exercise stderr at all.
$sb.AppendLine('echo STDERR_BURST 1>&2') | Out-Null
$sb.AppendLine('exit /b 0') | Out-Null
$fakeD = New-FakePio 'fake_d.bat' $sb.ToString()

# Extract the REAL Invoke-Pio from dev.ps1 (brace-balanced), so this test
# exercises the actual shipped code rather than a copy.
$src = [System.IO.File]::ReadAllText($DevPs1)
$startIdx = $src.IndexOf('function Invoke-Pio {')
if ($startIdx -lt 0) {
    Write-Output 'TOOLING_TEST_HARNESS_ERROR=Invoke-Pio not found in dev.ps1'
    exit 1
}
$depth = 0
$i = $src.IndexOf('{', $startIdx)
$end = -1
for ($j = $i; $j -lt $src.Length; $j++) {
    $c = $src[$j]
    if ($c -eq '{') { $depth++ }
    elseif ($c -eq '}') {
        $depth--
        if ($depth -eq 0) { $end = $j; break }
    }
}
$funcText  = $src.Substring($startIdx, $end - $startIdx + 1)
$extracted = Join-Path $tmp 'invoke_pio_extracted.ps1'
Set-Content -Path $extracted -Value $funcText -Encoding ASCII

$LogsDir = Join-Path $tmp 'logs'
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
function Assert-Pio { }

function Run($fakeExe) {
    $PioExe = $fakeExe
    . $extracted
    return (Invoke-Pio -PioArgs @() -LogName 'tooltest')
}

$rA = Run $fakeA
$rB = Run $fakeB
$rC = Run $fakeC
$rD = Run $fakeD

$Apass = ($rA -is [System.Management.Automation.PSCustomObject]) -and ($rA.ExitCode -eq 0)
$Bpass = ($rB -is [System.Management.Automation.PSCustomObject]) -and ($rB.ExitCode -eq 0)
$Cpass = ($rC -is [System.Management.Automation.PSCustomObject]) -and ($rC.ExitCode -eq 7)
$Dpass = ($rD -is [System.Management.Automation.PSCustomObject]) -and ($rD.ExitCode -eq 0) -and (@($rD).Count -eq 1)

Write-Output ("DEV_PS1_NATIVE_STDOUT_EXIT0_TEST_PASS=" + $(if ($Apass) { 'True' } else { 'False' }))
Write-Output ("DEV_PS1_NATIVE_STDERR_EXIT0_TEST_PASS=" + $(if ($Bpass) { 'True' } else { 'False' }))
Write-Output ("DEV_PS1_NATIVE_STDERR_EXIT7_TEST_PASS=" + $(if ($Cpass) { 'True' } else { 'False' }))
Write-Output ("DEV_PS1_SINGLE_RESULT_OBJECT_TEST_PASS=" + $(if ($Dpass) { 'True' } else { 'False' }))

if ($Apass -and $Bpass -and $Cpass -and $Dpass) { exit 0 } else { exit 1 }
