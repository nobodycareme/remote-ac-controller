@echo off
setlocal EnableExtensions

rem Double-click launcher for the capture-only IR Learning Studio.
rem It delegates to dev.ps1 and does not build, flash, or transmit IR.

set "SCRIPT_DIR=%~dp0"
set "DEV_PS1=%SCRIPT_DIR%dev.ps1"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if /I "%~1"=="--dry-run" (
    echo IR_LEARNING_STUDIO_LAUNCHER=%~f0
    echo IR_LEARNING_STUDIO_DEV_PS1=%DEV_PS1%
    if exist "%DEV_PS1%" (
        echo IR_LEARNING_STUDIO_DEV_PS1_EXISTS=True
    ) else (
        echo IR_LEARNING_STUDIO_DEV_PS1_EXISTS=False
    )
    echo IR_LEARNING_STUDIO_COMMAND=ir-learning-studio
    echo IR_LEARNING_STUDIO_AUTO_BUILD=False
    echo IR_LEARNING_STUDIO_AUTO_FLASH=False
    echo IR_LEARNING_STUDIO_AUTO_TRANSMIT=False
    exit /b 0
)

if not exist "%DEV_PS1%" (
    echo [ERROR] Cannot find dev.ps1:
    echo         "%DEV_PS1%"
    echo.
    echo Move this launcher back into Firmware\Remote_AC_Controller\tools and try again.
    pause
    exit /b 1
)

if not exist "%POWERSHELL_EXE%" (
    set "POWERSHELL_EXE=powershell.exe"
)

echo Starting IR Learning Studio...
echo Safety: no auto build, no auto flash, no auto IR transmit.
"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%DEV_PS1%" -Command ir-learning-studio
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] IR Learning Studio exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
