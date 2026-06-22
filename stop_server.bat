@echo off
setlocal
cd /d "%~dp0"
set PID_FILE=%~dp0server.pid
set PORT=8001

if not exist "%PID_FILE%" (
  goto :find_by_port
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
exit /b 0

:find_by_port
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  set PID=%%P
  goto :kill_found
)
echo No server.pid found and no listening server on port %PORT%.
endlocal
exit /b 0

:kill_found
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if errorlevel 1 (
  echo Found port %PORT% but process %PID% is not running anymore.
  endlocal
  exit /b 0
)

taskkill /PID %PID% /F >nul
if errorlevel 1 (
  echo Failed to stop server PID %PID% on port %PORT%.
  endlocal
  exit /b 1
)

if exist "%PID_FILE%" del "%PID_FILE%" >nul 2>nul
echo Server stopped on port %PORT%: PID %PID%.
endlocal
exit /b 0
