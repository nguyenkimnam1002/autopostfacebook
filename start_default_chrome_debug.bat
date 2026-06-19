@echo off
setlocal
set PORT=9222
set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe

if not exist "%CHROME%" (
  set CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
)

if not exist "%CHROME%" (
  echo Cannot find Chrome. Set CHROME path manually in this file.
  exit /b 1
)

echo Close all Chrome windows before running this file.
echo Starting your normal Chrome profile with remote debugging on port %PORT%...
start "" "%CHROME%" --remote-debugging-port=%PORT% --no-first-run --disable-default-apps https://shopee.vn
echo Opened Chrome. Return to the tool and click "Lay cookie tu Chrome".
endlocal
