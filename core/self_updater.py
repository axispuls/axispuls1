import os
import sys
import json
import time
import socket
import platform
import subprocess
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from .config_manager import get_base_dir
from .license_manager import SUPER_ADMIN_ID
from .bale_client import send_message

UPDATE_DIR = get_base_dir() / "updates"
UPDATE_FLAG_FILE = UPDATE_DIR / "update_done.json"

def get_current_executable_path() -> Path:
    """
    Returns the Path to the main application executable.
    In frozen mode: sys.executable.
    In dev mode: dist/AxisPuls_Setup.exe if exists, otherwise sys.executable.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve()
    dev_dist = get_base_dir() / "dist" / "AxisPuls_Setup.exe"
    if dev_dist.exists():
        return dev_dist.resolve()
    return Path(sys.executable).resolve()

def validate_update_file(file_path: Path) -> Tuple[bool, str]:
    """
    Validates whether the downloaded file is a genuine Windows executable (.exe).
    Checks existence, minimum size, and standard DOS/PE header ('MZ').
    """
    if not file_path.exists():
        return False, "فایل به‌روزرسانی یافت نشد."

    size = file_path.stat().st_size
    if size < 100 * 1024:  # Less than 100 KB is suspicious for a setup
        return False, f"حجم فایل بسیار کم و مشکوک است ({size} بایت)."

    try:
        with open(file_path, "rb") as f:
            header = f.read(2)
            if header != b"MZ":
                return False, "فایل دانلود شده یک فایل اجرایی معتبر ویندوز (EXE) نیست (سربرگ نامعتبر)."
    except Exception as e:
        return False, f"خطا در خواندن فایل به‌روزرسانی: {e}"

    return True, "فایل اجرایی معتبر است."

def record_update_flag(details: Dict[str, Any]):
    """Records update state before relaunching to send notification after startup."""
    try:
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_FLAG_FILE, "w", encoding="utf-8") as f:
            json.dump(details, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def check_and_notify_post_update(bot_token: str):
    """
    Checks if the application was just updated and restarted.
    If so, sends a confirmation notification to the Super Admin on Bale.
    """
    if not UPDATE_FLAG_FILE.exists():
        return

    try:
        with open(UPDATE_FLAG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    try:
        UPDATE_FLAG_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    sys_name = socket.gethostname()
    os_name = f"{platform.system()} {platform.release()}"
    ts = data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
    file_name = data.get("file_name", "AxisPuls_Setup.exe")

    notify_text = (
        f"🎉 **به‌روزرسانی با موفقیت انجام شد!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"نرم‌افزار «اکسیس پالس» با موفقیت به آخرین نسخه ارتقا یافت و هم‌اکنون به صورت خودکار راه‌اندازی و فعال شد.\n\n"
        f"🖥️ **سیستم:** `{sys_name}` ({os_name})\n"
        f"📦 **فایل نسخه جدید:** `{file_name}`\n"
        f"🕒 **زمان تکمیل:** `{ts}`\n"
        f"✅ کلیه فرآیندهای پایش و ارسال خودکار در وضعیت آماده‌باش هستند."
    )

    try:
        send_message(bot_token, str(SUPER_ADMIN_ID), notify_text)
    except Exception:
        pass

def apply_update_and_restart(new_file_path: Path) -> Tuple[bool, str]:
    """
    Performs out-of-process executable replacement and relaunch on Windows.
    1. Validates downloaded binary.
    2. Writes a detached .bat updater script.
    3. Launches the updater script and exits the current process.
    """
    ok, msg = validate_update_file(new_file_path)
    if not ok:
        return False, msg

    target_exe = get_current_executable_path()
    current_pid = os.getpid()

    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    bat_file = UPDATE_DIR / "apply_update.bat"

    # Flag for post-update confirmation
    record_update_flag({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_exe": str(target_exe),
        "file_name": new_file_path.name,
        "pid": current_pid
    })

    bat_content = f"""@echo off
chcp 65001 >nul
echo Axis Puls Remote Self-Updater Running...
timeout /t 2 /nobreak >nul

:: Terminate current process if still active
taskkill /F /PID {current_pid} >nul 2>&1
taskkill /F /IM AxisPuls_Setup.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: Retry copying up to 10 times in case of file handle delays
set count=0
:retry_copy
set /a count+=1
copy /y "{str(new_file_path.resolve())}" "{str(target_exe.resolve())}" >nul 2>&1
if %errorlevel% neq 0 (
    if %count% leq 10 (
        timeout /t 1 /nobreak >nul
        goto retry_copy
    )
)

:: Clean up downloaded temp file
del /f /q "{str(new_file_path.resolve())}" >nul 2>&1

:: Relaunch updated executable
start "" "{str(target_exe.resolve())}" --updated-by-bot

:: Remove batch script
del "%~f0" >nul 2>&1
exit
"""

    try:
        with open(bat_file, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except Exception as e:
        return False, f"خطا در ایجاد اسکریپت به‌روزرسانی: {e}"

    # Launch batch file detached
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_file)],
            cwd=str(get_base_dir()),
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True
        )
        return True, "اسکریپت جایگزینی و به‌روزرسانی آغاز شد. نرم‌افزار تا لحظاتی دیگر ریستارت می‌شود."
    except Exception as e:
        return False, f"خطا در اجرای اسکریپت به‌روزرسانی: {e}"
