import os
import time
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from .file_watcher import get_latest_file
from .state_manager import is_file_already_sent, load_state

REPORT_INTERVAL_SECONDS = 300  # 5 minutes in seconds

def check_bale_connectivity() -> Tuple[bool, str]:
    """Tests internet connectivity and latency to Bale server with a short timeout."""
    try:
        import requests
        from .ssl_helper import apply_ssl_fix
        t0 = time.time()
        ca = apply_ssl_fix()
        r = requests.get("https://tapi.bale.ai", timeout=2.5, verify=ca)
        lat = int((time.time() - t0) * 1000)
        return True, f"🟢 متصل به سرور بله (تاخیر: {lat} میلی‌ثانیه)"
    except Exception:
        return False, "🔴 اختلال در اتصال به سرور بله یا قطعی اینترنت"

def get_system_resource_metrics(target_dir: str) -> Dict[str, str]:
    """Retrieves disk free space and process/system RAM metrics."""
    res = {}
    try:
        check_path = target_dir if (target_dir and os.path.exists(target_dir)) else os.path.abspath(".")
        total, used, free = shutil.disk_usage(check_path)
        free_gb = free / (1024 ** 3)
        res["disk_free"] = f"{free_gb:.1f} گیگابایت فضای خالی"
    except Exception:
        res["disk_free"] = "نامشخص"

    try:
        import psutil
        mem = psutil.virtual_memory()
        free_ram_gb = mem.available / (1024 ** 3)
        proc = psutil.Process()
        proc_mb = proc.memory_info().rss / (1024 * 1024)
        res["ram"] = f"مصرف برنامه: {proc_mb:.0f} MB | رم آزاد سیستم: {free_ram_gb:.1f} GB"
    except Exception:
        res["ram"] = "نامشخص"
    return res

def format_remaining_time(seconds: int) -> str:
    """Formats remaining seconds into a clear Persian time string."""
    if seconds <= 0:
        return "هم‌اکنون (در حال ارسال)"
    mins = seconds // 60
    secs = seconds % 60
    if mins > 0 and secs > 0:
        return f"{mins} دقیقه و {secs} ثانیه"
    elif mins > 0:
        return f"{mins} دقیقه"
    else:
        return f"{secs} ثانیه"

def generate_5min_status_report(
    folder_path: str,
    active_users_count: int,
    next_send_epoch: float,
    interval_minutes: int
) -> Dict[str, Any]:
    """
    Generates a detailed, deep status report for the 5-minute inspection cycle:
    - Checks whether a new file exists in the folder
    - Identifies what the file is (name, size, mtime)
    - Calculates exact remaining minutes/seconds until next send
    - Produces a formatted report text for GUI and logs
    """
    now = time.time()
    remaining_seconds = max(0, int(round(next_send_epoch - now)))
    remaining_str = format_remaining_time(remaining_seconds)
    next_send_dt = datetime.fromtimestamp(next_send_epoch)
    next_send_str = next_send_dt.strftime("%H:%M:%S")
    now_dt = datetime.fromtimestamp(now)
    now_str = now_dt.strftime("%H:%M:%S")

    # If folder is invalid
    if not folder_path or not os.path.isdir(folder_path):
        text = (
            "=======================================================\n"
            f"🔍 [گزارش وضعیت ۵ دقیقه‌ای سامانه] - ساعت {now_str}\n"
            f"📁 مسیر پوشه: {folder_path or 'مشخص نشده'}\n"
            "⚠️ خطا: پوشه مورد نظر معتبر نیست یا روی سیستم یافت نشد.\n"
            "======================================================="
        )
        return {
            "is_valid": False,
            "has_new_file": False,
            "remaining_seconds": remaining_seconds,
            "report_text": text
        }

    latest_file = get_latest_file(folder_path)

    # If folder has no valid files
    if not latest_file:
        _, net_status = check_bale_connectivity()
        sys_metrics = get_system_resource_metrics(folder_path)
        text = (
            "=======================================================\n"
            f"🔍 [گزارش وضعیت ۵ دقیقه‌ای سامانه] - ساعت {now_str}\n"
            f"📁 پوشه تحت پایش: {folder_path}\n"
            "📂 محتوای پوشه: هیچ فایل معتبری در پوشه یافت نشد.\n"
            f"⏳ زمان تا دور بعدی بررسی: ۵ دقیقه دیگر\n"
            f"👥 تعداد گیرندگان بله: {active_users_count} کاربر\n"
            f"🌐 وضعیت اتصال: {net_status}\n"
            f"💾 دیسک پوشه: {sys_metrics.get('disk_free', 'نامشخص')}\n"
            "======================================================="
        )
        return {
            "is_valid": True,
            "has_new_file": False,
            "latest_file": None,
            "remaining_seconds": remaining_seconds,
            "report_text": text
        }

    # A file exists in the folder: check if it's new or already sent
    already_sent = is_file_already_sent(latest_file)
    is_new = not already_sent
    fname = latest_file["name"]
    fsize = latest_file["readable_size"]
    fmtime = latest_file["formatted_mtime"]
    size_bytes = latest_file["size"]

    if size_bytes > 20 * 1024 * 1024:
        size_note = f"{fsize} (بیش از ۲۰ مگابایت -> ارسال به صورت پارت‌های زیپ)"
    else:
        size_note = f"{fsize} (زیر ۲۰ مگابایت -> ارسال مستقیم)"

    if is_new:
        status_line = f"🟢 بله، فایل جدید است و در صف ارسال قرار دارد!"
        timing_action = f"🚀 طبق برنامه، ارسال این فایل به صورت خودکار به بله انجام می‌شود."
    else:
        state = load_state()
        last_sent_at = state.get("last_sent_at", "نامشخص")
        status_line = f"⚪ خیر، فایل جدیدی نیست (این فایل قبلاً در تاریخ {last_sent_at} ارسال شده است)."
        timing_action = f"🟢 وضعیت: فایل ارسال شده است. سامانه در حالت آماده‌باش و در انتظار ورود فایل جدید می‌باشد (ارسال مجدد تا آمدن فایل جدید انجام نخواهد شد)."

    # Gather operational health metrics
    state = load_state()
    history = state.get("history", [])
    total_sent = len(history)
    last_sent_name = state.get("last_sent_file", "هیچ فایلی")
    last_sent_time = state.get("last_sent_at", "نامشخص")

    _, net_status = check_bale_connectivity()
    sys_metrics = get_system_resource_metrics(folder_path)

    text = (
        "=======================================================\n"
        f"📊 [گزارش بررسی وضعیت پوشه و زمان ارسال - دوره ۵ دقیقه‌ای]\n"
        f"🕒 ساعت ثبت گزارش: {now_str}\n"
        f"📁 پوشه تحت پایش: {folder_path}\n"
        f"📄 آخرین فایل موجود: {fname}\n"
        f"📊 حجم فایل: {size_note}\n"
        f"🕒 تاریخ آخرین تغییر فایل: {fmtime}\n"
        f"🔎 وضعیت تازگی: {status_line}\n"
        f"⏳ وضعیت عملکرد: {timing_action}\n"
        f"👥 گیرندگان فعال در بله: {active_users_count} کاربر\n"
        f"🌐 وضعیت اتصال: {net_status}\n"
        f"💾 دیسک پوشه: {sys_metrics.get('disk_free', 'نامشخص')}\n"
        f"🧠 منابع سیستم: {sys_metrics.get('ram', 'نامشخص')}\n"
        f"📈 آمار کل: {total_sent} فایل موفق تا کنون | آخرین ارسال: {last_sent_name} ({last_sent_time})\n"
        "======================================================="
    )

    return {
        "is_valid": True,
        "has_new_file": is_new,
        "latest_file": latest_file,
        "remaining_seconds": remaining_seconds,
        "remaining_str": remaining_str,
        "next_send_str": next_send_str,
        "report_text": text
    }
