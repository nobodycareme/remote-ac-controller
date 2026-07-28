@echo off
set "SCRIPT_DIR=%~dp0"
set "PY="
if exist "%SCRIPT_DIR%..\..\Environment\Python\python.exe" set "PY=%SCRIPT_DIR%..\..\Environment\Python\python.exe"
if not defined PY if exist "C:\Users\user\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PY=C:\Users\user\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PY set "PY=python"
chcp 65001 >nul
echo Using Python: %PY%
"%PY%" -u "%SCRIPT_DIR%ir_capture_console.py" --count 10 --start-index 4
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [ERROR] tool exited with code %RC%. See messages above.
pause
