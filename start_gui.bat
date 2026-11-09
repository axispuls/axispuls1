@echo off
chcp 65001 >nul
title نرم‌افزار اکسیس پالس (Axis Puls)
cd /d "%~dp0"
start "" pythonw.exe gui_app.py
if %errorlevel% neq 0 (
    python.exe gui_app.py
)
exit
