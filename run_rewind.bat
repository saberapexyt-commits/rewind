@echo off
REM First run installs what Rewind needs, then starts it with no console window.
cd /d "%~dp0"
python -c "import webview, pystray, pyaudiowpatch, numpy" 2>nul || python -m pip install -r requirements.txt
start "" pythonw app.py
