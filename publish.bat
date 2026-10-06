@echo off
REM Uploads Rewind to GitHub, turns on the website, and builds the exe in the cloud.
cd /d "%~dp0"
python publish.py %*
echo.
pause
