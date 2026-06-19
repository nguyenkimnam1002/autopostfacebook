@echo off
setlocal
cd /d "%~dp0"
set PID_FILE=%~dp0server.pid

if not exist "%PID_FILE%" (
  echo No server.pid found. Nothing to stop.
  exit /b 0
)

set /p PID=<"%PID_FILE%"
if "%PID%"=="" (
  del "%PID_FILE%" >nul 2>nul
  echo Empty PID file removed.
  exit /b 0
)

tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if errorlevel 1 (
  del "%PID_FILE%" >nul 2>nul
  echo Server PID %PID% is not running. PID file removed.
  exit /b 0
)

taskkill /PID %PID% /F >nul
if errorlevel 1 (
  echo Failed to stop server PID %PID%.
  exit /b 1
)

del "%PID_FILE%" >nul 2>nul
echo Server stopped: PID %PID%.
endlocal
