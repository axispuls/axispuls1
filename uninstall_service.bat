@echo off
chcp 65001 >nul
title غیرفعال‌سازی و حذف سرویس پایش بله
cd /d "%~dp0"

echo ======================================================
echo          توقف و حذف سرویس خودکار پایش بله
echo ======================================================
echo.

python -c "from core.service_manager import remove_full_autostart, stop_worker_process; remove_full_autostart(); stop_worker_process(); print('سرویس پس‌زمینه متوقف و از استارت‌آپ ویندوز حذف شد.')"

echo.
echo ======================================================
echo حذف با موفقیت انجام شد.
echo ======================================================
pause
