@echo off
chcp 65001 >nul
title Violet Reach
netstat -an | findstr /C:":5199" | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo Violet Reach läuft bereits - öffne Browser.
  start http://localhost:5199/
  exit /b
)
cd /d "%~dp0"
echo Pruefe auf Updates...
git pull --ff-only
if errorlevel 1 echo Hinweis: Update uebersprungen - starte lokale Version.
cd web\explore
call npm install --no-audit --no-fund
if errorlevel 1 goto npmfail
echo Starte Violet Reach - dieses Fenster offen lassen!
start "" cmd /c "timeout /t 6 >nul & start http://localhost:5199/"
set VR_GATE_CACHE_MS=30000
call npm run dev -- --port 5199 --strictPort
goto end
:npmfail
echo FEHLER: npm install fehlgeschlagen. Ist Node.js installiert?
:end
pause
