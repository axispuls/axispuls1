@echo off
chcp 65001 >nul
title نصب سرویس اکسیس پالس (Axis Puls)
cd /d "%~dp0"

echo ======================================================
echo    نصب و فعال‌سازی سرویس دائمی اکسیس پالس (Axis Puls)
echo ======================================================
echo.

python -c "from core.service_manager import setup_full_autostart, start_worker_process; ok, msg = setup_full_autostart(); print(msg); start_worker_process(); print('سرویس پس‌زمینه با موفقیت فعال شد.')"

echo.
echo ======================================================
echo نصب با موفقیت پایان یافت. این سرویس حتی پس از خاموش یا
echo روشن شدن سیستم همواره در پس‌زمینه فعال خواهد بود.
echo ======================================================
pause
