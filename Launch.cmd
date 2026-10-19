@echo off
cd /d "%~dp0"
python -m opencal
if errorlevel 1 pause
