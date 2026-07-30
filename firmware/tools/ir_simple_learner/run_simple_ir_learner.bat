@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON="
:: 1. Explicit interpreter via the IR_PYTHON environment variable
if defined IR_PYTHON if exist "%IR_PYTHON%" (
    set "PYTHON=%IR_PYTHON%"
    goto :found
)
:: 2. Repository-local virtual environment, if one was created
if exist "%~dp0..\..\..\.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0..\..\..\.venv\Scripts\python.exe"
    goto :found
)
:: 3. Try system Python
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
