@echo off
cd /d "%~dp0"
start "" "%~dp0Rylume.exe" --port 8779 --no-migrate
