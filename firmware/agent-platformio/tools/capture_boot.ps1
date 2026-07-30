# capture_boot.ps1 — 非交互串口启动日志采集（§四/§十 证据）
# 用法: .\capture_boot.ps1 -Port COM6 -Baud 115200 -Seconds 50 -Out boot.log
param(
    [string]$Port = 'COM6',
    [int]$Baud = 115200,
    [int]$Seconds = 50,
    [string]$Out = 'boot_capture.log'
)
$ErrorActionPreference = 'SilentlyContinue'
try {
    $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
    $sp.ReadTimeout = 1000
    $sp.WriteTimeout = 1000
    # 打开即触发 DTR/RTS 变化，可能复位 ESP；这正是我们想要的干净 boot。
    $sp.DtrEnable = $true
    $sp.RtsEnable = $true
    $sp.Open()
    Start-Sleep -Milliseconds 200
    $sp.DtrEnable = $false   # 释放复位
    $sp.RtsEnable = $false
    Start-Sleep -Milliseconds 100
} catch {
    Write-Output ("CAPTURE_OPEN_FAIL: " + $_.Exception.Message)
    exit 2
}
$lines = @()
$start = Get-Date
$buf = ''
try {
    while (((Get-Date) - $start).TotalSeconds -lt $Seconds) {
        if ($sp.BytesToRead -gt 0) {
            $c = $sp.ReadExisting()
            $buf += $c
            while ($buf.Contains("`n")) {
                $i = $buf.IndexOf("`n")
                $line = $buf.Substring(0, $i).TrimEnd("`r")
                $buf = $buf.Substring($i + 1)
                $lines += $line
                Write-Output $line
            }
        } else {
            Start-Sleep -Milliseconds 50
        }
    }
    if ($buf.Length -gt 0) { $lines += $buf.TrimEnd("`r"); Write-Output $buf }
} finally {
    $sp.Close()
}
$lines | Out-File -FilePath $Out -Encoding utf8
Write-Output ("CAPTURE_LINES=" + $lines.Count + " OUT=" + $Out)
exit 0
