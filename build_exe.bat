@echo off
REM Builds dist\Rewind\Rewind.exe on this PC. Needs Python 3.10+.
REM Afterwards copy ffmpeg.exe and ffprobe.exe (version 6 or newer) into dist\Rewind next to Rewind.exe.
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --noconsole --name Rewind --icon rewind.ico ^
  --add-data "ui;ui" --add-data "rewind.ico;." --add-data "logo.png;." ^
  --hidden-import pystray._win32 --hidden-import games --distpath dist\Rewind app.py
echo.
echo Done: dist\Rewind\Rewind.exe
echo Next: put ffmpeg.exe and ffprobe.exe in dist\Rewind next to it.
pause
