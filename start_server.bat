@echo off
setlocal
cd /d "%~dp0"
set HOST=127.0.0.1
set PORT=8001
set PID_FILE=%~dp0server.pid

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  set EXISTING_PID=%%P
  goto :port_in_use
)

for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path; $p=Start-Process -FilePath python -ArgumentList '-m','affiliate_tool.cli','web','--host','127.0.0.1','--port','8001' -WorkingDirectory $root -WindowStyle Hidden -PassThru; $p.Id"`) do set NEW_PID=%%P

if "%NEW_PID%"=="" (
  echo Failed to start server.
  exit /b 1
)

echo %NEW_PID%>"%PID_FILE%"
echo Server started with PID %NEW_PID%.
echo Open http://%HOST%:%PORT%/affiliate_hot_tool
start "" "http://%HOST%:%PORT%/affiliate_hot_tool"
endlocal
exit /b 0

:port_in_use
for /f "usebackq delims=" %%L in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq %EXISTING_PID% }; if($p){$p.CommandLine}"`) do set CMDLINE=%%L
echo %CMDLINE% | find /I "affiliate_tool.cli web" >nul
if not errorlevel 1 (
  echo %EXISTING_PID%>"%PID_FILE%"
  echo Server da dang chay san tren port %PORT% voi PID %EXISTING_PID%.
  echo Da dong bo lai server.pid.
  echo Open http://%HOST%:%PORT%/affiliate_hot_tool
  start "" "http://%HOST%:%PORT%/affiliate_hot_tool"
  endlocal
  exit /b 0
)

echo Port %PORT% is already in use by PID %EXISTING_PID%. Stop it first with stop_server.bat.
endlocal
exit /b 1
