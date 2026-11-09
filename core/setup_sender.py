import os
import shutil
import time
from pathlib import Path
from typing import List, Callable, Optional, Tuple, Dict, Any

from .config_manager import get_base_dir
from .self_updater import get_current_executable_path
from .archiver import prepare_file_for_sending, format_file_size, MAX_SINGLE_FILE_SIZE
from .bale_client import send_message, send_document

SETUP_TEMP_DIR = get_base_dir() / "updates" / "temp_setup_parts"

# Safe chunk size for Bale upload: 18 MB (always strictly below the 20 MB ceiling)
SAFE_SETUP_PART_SIZE = 18 * 1024 * 1024

def send_application_setup(
    bot_token: str,
    target_user_ids: List[str],
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[str, int, int, int], None]] = None
) -> Tuple[bool, str]:
    """
    Safely sends the application executable setup file (AxisPuls_Setup.exe, ~50MB) to the given users.
    Compresses and splits into <= 18 MB parts to strictly obey Bale's 20 MB limit.
    """
    cur_exe = get_current_executable_path()
    if not cur_exe.exists():
        msg = f"⚠️ فایل ستاپ در مسیر «{cur_exe.name}» یافت نشد."
        if log_callback:
            log_callback(msg)
        return False, msg

    raw_size = cur_exe.stat().st_size
    size_mb = round(raw_size / (1024 * 1024), 2)
    start_msg = f"📦 آماده‌سازی آخرین نسخه نرم‌افزار ({cur_exe.name} | {size_mb} MB) جهت ارسال امن..."
    if log_callback:
        log_callback(start_msg)

    # Clean working temp dir
    if SETUP_TEMP_DIR.exists():
        try:
            shutil.rmtree(SETUP_TEMP_DIR)
        except Exception:
            pass
    SETUP_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Prepare and split into <= 18 MB parts
        prep_result = prepare_file_for_sending(
            str(cur_exe),
            str(SETUP_TEMP_DIR),
            max_size=MAX_SINGLE_FILE_SIZE,
            part_size=SAFE_SETUP_PART_SIZE,
            compression_method="deflate_max",
            auto_compress_all=True
        )

        parts = prep_result["parts"]
        total_parts = len(parts)

        info_text = (
            f"🚀 **ارسال آخرین نسخه نرم‌افزار اکسیس پالس**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 **نام فایل ستاپ:** `{cur_exe.name}`\n"
            f"📊 **حجم کل فایل:** {size_mb} مگابایت\n"
            f"🧩 **ساختار ارسال:** {total_parts} پارت زیپ استاندارد (جهت رعایت سقف ۲۰ مگابایت بله)\n"
            f"⏳ در حال ارسال پارت‌ها، لطفاً شکیبا باشید..."
        )

        for uid in target_user_ids:
            cid = str(uid).strip()
            if cid:
                send_message(bot_token, cid, info_text)

        # Send each part
        success_parts = 0
        for part in parts:
            p_num = part["part_number"]
            p_name = part["filename"]
            p_path = part["path"]
            p_size_str = part.get("readable_size", "")

            caption = (
                f"📦 پارت {p_num} از {total_parts} | آخرین نسخه اکسیس پالس\n"
                f"🏷 فایل: `{p_name}` ({p_size_str})\n"
                f"💡 راهنما: پس از دریافت تمام پارت‌ها، پارت اول (.zip.001) را اکسترکت نمایید."
            )

            if log_callback:
                log_callback(f"در حال آپلود {p_name} (پارت {p_num}/{total_parts} | {p_size_str}) به بله...")

            part_ok_all = True
            for uid in target_user_ids:
                cid = str(uid).strip()
                if not cid:
                    continue

                part_cb = None
                if progress_callback:
                    part_cb = lambda pct, b_read, b_tot, target_cid=cid: progress_callback(target_cid, pct, b_read, b_tot)

                ok, err = send_document(
                    bot_token,
                    cid,
                    p_path,
                    caption=caption,
                    log_callback=log_callback,
                    progress_callback=part_cb
                )
                if not ok:
                    part_ok_all = False
                    if log_callback:
                        log_callback(f"❌ خطا در ارسال پارت {p_num} به {cid}: {err}")

            if part_ok_all:
                success_parts += 1
                if log_callback:
                    log_callback(f"✅ پارت {p_num} از {total_parts} با موفقیت ارسال شد.")

        if success_parts == total_parts:
            done_msg = (
                f"🎉 **ارسال آخرین نسخه نرم‌افزار با موفقیت به پایان رسید!**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• تعداد پارت‌های تحویل‌شده: {total_parts} پارت ({size_mb}MB)\n\n"
                f"📥 **راهنمای نصب و استخراج فایل تک‌پارت ستاپ:**\n"
                f"۱. فایل‌های دریافتی را در یک پوشه قرار دهید.\n"
                f"۲. کافیست روی پارت اول (`.zip.001`) راست‌کلیک کرده و با **WinRAR** یا **7-Zip** گزینه `Extract Here` را بزنید تا فایل نصبی `{cur_exe.name}` بلافاصله ایجاد شود.\n"
                f"۳. یا در خط فرمان ویندوز (CMD) در همان پوشه دستور زیر را وارد کنید:\n"
                f"`copy /b {cur_exe.stem}.zip.* {cur_exe.stem}.zip`"
            )
            for uid in target_user_ids:
                cid = str(uid).strip()
                if cid:
                    send_message(bot_token, cid, done_msg)
            return True, f"تمام {total_parts} پارت نسخه جدید با موفقیت ارسال شدند."
        else:
            return False, f"تنها {success_parts} از {total_parts} پارت ارسال شدند."

    except Exception as e:
        err_msg = f"خطا در آماده‌سازی و ارسال پارت‌های ستاپ: {e}"
        if log_callback:
            log_callback(err_msg)
        return False, err_msg
    finally:
        if SETUP_TEMP_DIR.exists():
            try:
                shutil.rmtree(SETUP_TEMP_DIR)
            except Exception:
                pass
