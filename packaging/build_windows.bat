@echo off
REM Windows: builds dist\SoundDial\SoundDial.exe with PyInstaller.
cd /d "%~dp0\.."
python -m pip install --quiet --upgrade pyinstaller PySide6 pycaw comtypes psutil pillow
python tools\make_icons.py
pyinstaller --noconfirm --clean packaging\sounddial.spec
echo Built: dist\SoundDial\SoundDial.exe
pause
