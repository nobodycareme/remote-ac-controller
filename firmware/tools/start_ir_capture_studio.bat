@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  红外学习采集台 — ZJ-IR-V2 启动器
REM  双击本文件即可打开 GUI（异常时保留窗口，不静默关闭）
REM ============================================================
cd /d "C:\example\remote-ac\Firmware\Remote_AC_Controller\tools"
set "TOOL_DIR=%CD%\ir_capture_studio"

REM ---- 1. 选择 Python 解释器（优先 py 启动器，其次 python）----
set "PYTHON_EXE="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_EXE=py -3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 ( set "PYTHON_EXE=python" )
)

if "%PYTHON_EXE%"=="" (
    echo [错误] 未检测到 Python。请安装 Python 3 并将其加入 PATH。
    echo         下载：https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---- 2. 检查 pyserial 是否可用 ----
%PYTHON_EXE% -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo [错误] 未安装 pyserial，无法连接 CH9102 设备。
    echo         请运行： %PYTHON_EXE% -m pip install pyserial
    pause
    exit /b 1
)

REM ---- 3. 启动 GUI ----
echo 正在启动 红外学习采集台 — ZJ-IR-V2 ...
%PYTHON_EXE% "%TOOL_DIR%\app.py"
if errorlevel 1 (
    echo [错误] 程序异常退出，请根据上方日志排查。
    pause
    exit /b 1
)

pause
