@echo off
REM Windows: double-click. Starts the engine and opens SoundDial in your browser.
cd /d "%~dp0"
py engine.py --open || python engine.py --open
pause
