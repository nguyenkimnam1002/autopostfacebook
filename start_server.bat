@echo off
setlocal
cd /d "%~dp0"
set HOST=127.0.0.1
set PORT=8001
set PID_FILE=%~dp0server.pid

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  echo Port %PORT% is already in use by PID %%P. Stop it first with stop_server.bat.
  exit /b 1
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
