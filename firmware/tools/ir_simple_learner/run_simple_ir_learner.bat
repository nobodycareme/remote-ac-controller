@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON="
:: Try project managed Python first (has pyserial installed)
if exist "C:\Users\user\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
    set "PYTHON=C:\Users\user\.workbuddy\binaries\python\versions\3.13.12\python.exe"
    goto :found
)
:: Try system Python
for %%p in (python3.exe python.exe) do (
    where %%p >nul 2>&1 && set "PYTHON=%%p" && goto :found
)
:found
if "%PYTHON%"=="" (
    echo [ERROR] Python not found. Install Python 3.9+ and pyserial.
    pause
    exit /b 1
)
echo Python: %PYTHON%
%PYTHON% -c "import serial" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pyserial not installed.
    echo Install: %PYTHON% -m pip install pyserial
    pause
    exit /b 1
)
if "%1"=="--self-test" (
    echo Running unit tests...
    %PYTHON% -m unittest discover -s tests -p "test_*.py" -v
    pause
    exit /b %ERRORLEVEL%
)
if "%1"=="--simulate-capture" (
    echo Running simulated capture...
    %PYTHON% simple_ir_learner.py --simulate-capture
    pause
    exit /b %ERRORLEVEL%
)
echo Starting IR Simple Learner...
%PYTHON% simple_ir_learner.py
if %ERRORLEVEL% NEQ 0 pause
