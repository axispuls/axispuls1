import os
import sys
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Add root directory to sys.path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Fix PyInstaller onefile CA bundle bug when parent GUI window closes
from core.ssl_helper import apply_ssl_fix
apply_ssl_fix()

from core.config_manager import load_config, get_active_user_ids, get_base_dir
from core.state_manager import (
    is_file_already_sent,
    record_sent_file,
    load_state,
    set_next_send_epoch,
    get_next_send_epoch,
    get_last_upload_speed,
    is_folder_baselined,
    baseline_folder_contents
)
from core.file_watcher import get_latest_file, format_file_size
from core.bale_client import (
    broadcast_document,
    broadcast_message,
    send_message_async,
    broadcast_message_async,
    send_message_with_id,
    delete_messages_async
)
from core.archiver import (
    prepare_file_for_sending,
    get_adaptive_part_size,
    PART_SIZE_SLOW,
    PART_SIZE_FAST
)
from core.bale_listener import BaleBotListener
from core.security_utils import validate_safe_folder, mask_token
from core.reporter import generate_5min_status_report, REPORT_INTERVAL_SECONDS
from core.license_manager import is_license_active
from core.self_updater import check_and_notify_post_update

LOG_FILE = get_base_dir() / "service.log"
LOCK_FILE = get_base_dir() / "service.lock"
TEMP_DIR = get_base_dir() / "temp_parts"

# Setup logging
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

def log_and_print(msg: str, level: str = "info"):
    try:
        if sys.stdout:
            print(msg)
    except Exception:
        pass
    if level == "error":
        logging.error(msg)
    elif level == "warning":
        logging.warning(msg)
    else:
        logging.info(msg)

def acquire_lock() -> bool:
    """Acquires a single instance lock via Windows lock file."""
    try:
        if LOCK_FILE.exists():
            try:
                with open(LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                import psutil
                if psutil.pid_exists(old_pid):
                    proc = psutil.Process(old_pid)
                    pname = proc.name().lower()
                    current_name = Path(sys.executable).name.lower()
                    if "python" in pname or "baleworker" in pname or "axispuls" in pname or pname == current_name:
                        log_and_print(f"نسخه دیگری از سرویس با PID {old_pid} در حال اجراست.", "warning")
                        return False
            except Exception:
                pass
        
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        log_and_print(f"خطا در ایجاد قفل سرویس: {e}", "warning")
        return True

def release_lock():
    """Removes the lock file on exit."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass

def _make_progress_bar(pct: int) -> str:
    filled = max(0, min(10, int(round(pct / 10))))
    empty = 10 - filled
    return f"[{'█' * filled}{'░' * empty}]"

def perform_send(log_if_duplicate: bool = True) -> bool:
    """
    Executes sending of the latest file to active Bale users.
    - Reports file arrival, size, and part count to user in Bale.
    - Reports 20% progress milestones during upload.
    - If size <= 10 MB: sends directly.
    - If size > 10 MB: compresses and sends as multi-part zip archives.
    - Reports delivery confirmation and records sent file upon success.
    """
    config = load_config()
    raw_folder = config.get("folder_path", "").strip()
    bot_token = config.get("bot_token", "").strip()
    active_users = get_active_user_ids(config)

    is_valid, msg_folder, safe_path = validate_safe_folder(raw_folder)
    if not is_valid:
        log_and_print(f"خطا در پوشه: {msg_folder}", "warning")
        return False

    folder_path = str(safe_path)

    if not bot_token:
        log_and_print("توکن ربات بله مشخص نشده است.", "warning")
        return False

    if not active_users:
        log_and_print("هیچ آیدی عددی کاربری برای ارسال مشخص نشده است.", "warning")
        return False

    latest_file = get_latest_file(folder_path)
    if not latest_file:
        if log_if_duplicate:
            log_and_print("هیچ فایل معتبری در پوشه جهت ارسال یافت نشد.")
        return False

    if is_file_already_sent(latest_file):
        if log_if_duplicate:
            log_and_print(f"فایل «{latest_file['name']}» قبلاً ارسال شده است و فایل جدیدی وجود ندارد.")
        return False

    # New file found - proceed with delivery
    file_name = latest_file["name"]
    file_path = latest_file["path"]
    size_str = latest_file["readable_size"]
    mtime_str = latest_file["formatted_mtime"]

    log_and_print(f"🚀 در حال آماده‌سازی و ارسال آخرین فایل: {file_name} ({size_str}) ...")

    if TEMP_DIR.exists():
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception:
            pass

    try:
        # Determine adaptive part size based on network upload speed (< 0.5 MB/s -> 10 MB, >= 0.5 MB/s -> 20 MB)
        measured_speed = get_last_upload_speed()
        adaptive_part_size = get_adaptive_part_size(measured_speed)
        part_size_mb = 20 if adaptive_part_size == PART_SIZE_FAST else 10
        speed_tag = f"{(measured_speed / (1024*1024)):.2f} MB/s" if measured_speed > 0 else "پیش‌فرض"
        log_and_print(f"📊 وضعیت سرعت شبکه: {speed_tag} -> اندازه پارت‌های زیپ: {part_size_mb} مگابایت تنظیم گردید.")

        compression_method = config.get("compression_mode", "deflate_max")
        auto_compress_all = config.get("auto_compress_all", False)
        prep_result = prepare_file_for_sending(
            file_path,
            str(TEMP_DIR),
            part_size=adaptive_part_size,
            compression_method=compression_method,
            auto_compress_all=auto_compress_all
        )
        parts = prep_result["parts"]
        is_split = prep_result["is_split"]
        total_parts = len(parts)
        was_compressed = prep_result.get("was_compressed", False)

        if is_split:
            struct_text = f"چندبخشی ({total_parts} پارت زیپ - هر پارت حداکثر {part_size_mb} مگابایت بر اساس سرعت شبکه)"
            log_and_print(f"حجم فایل بیش از {part_size_mb} مگابایت است. فایل به {total_parts} پارت زیپ تقسیم شد.")
        elif was_compressed:
            struct_text = "تک‌پارت فشرده‌شده (۱ فایل زیپ)"
            log_and_print("فایل فشرده‌سازی شد و به صورت تک‌پارت ارسال می‌گردد.")
        else:
            struct_text = "تک‌پارت (ارسال یکپارچه با فرمت اصلی)"

        if was_compressed and compression_method == "lzma_ultra":
            comp_text = "فعال (فشرده‌سازی حداکثری اولترا LZMA Ultra)"
        elif was_compressed:
            comp_text = "فعال (فشرده‌سازی استاندارد Deflate 9)"
        else:
            comp_text = "غیرفعال (ارسال فایل بدون فشرده‌سازی)"

        # 1. Report new file arrival, size, and parts to all users in Bale
        arrival_msg = (
            "📥 فایل جدید در سیستم دریافت شد!\n\n"
            f"📄 نام فایل: {file_name}\n"
            f"📊 حجم اصلی فایل: {size_str}\n"
            f"📦 ساختار ارسال: {struct_text}\n"
            f"⚙️ وضعیت فشرده‌سازی: {comp_text}\n"
            f"🕒 تاریخ آخرین تغییر: {mtime_str}\n\n"
            "⏳ فرآیند آماده‌سازی و ارسال به ربات بله آغاز گردید..."
        )
        broadcast_message(bot_token, active_users, arrival_msg)

        all_parts_success = True
        # Tracker for percentage progress message IDs to clean up after upload completes
        progress_msg_tracker: List[Tuple[str, int]] = []

        for part in parts:
            part_path = part["path"]
            part_num = part["part_number"]
            part_size_str = part.get("readable_size", "")
            size_tag = f" | حجم: {part_size_str}" if part_size_str else ""
            caption_note = part.get("caption_note", "")

            caption_lines = [
                "📎 دریافت خودکار آخرین فایل",
                f"🏷 نام فایل اصلی: {file_name}",
                f"📊 حجم اصلی: {size_str}",
                f"🕒 تاریخ آخرین تغییر: {mtime_str}"
            ]
            if is_split:
                caption_lines.append(f"📦 بخش: پارت {part_num} از {total_parts}{size_tag}")
            if caption_note:
                caption_lines.append(caption_note)
            caption_lines.append("🤖 ارسال خودکار توسط سرویس پایش")

            caption = "\n".join(caption_lines)

            # 2. Callback for real-time 20% milestone progress reporting + message ID tracking
            def _create_part_progress_cb(p_num: int, p_tot: int, p_fname: str):
                def _on_progress(target_cid: str, pct: int, bytes_read: int, total_bytes: int):
                    bar = _make_progress_bar(pct)
                    read_str = format_file_size(bytes_read)
                    tot_str = format_file_size(total_bytes)

                    if p_tot > 1:
                        target_label = f"پارت {p_num} از {p_tot}"
                    else:
                        target_label = f"«{file_name}»"

                    if pct == 100:
                        prog_text = (
                            f"✅ ۱۰۰٪ آپلود شد!\n"
                            f"{bar} ۱۰۰٪\n"
                            f"در حال ثبت و تحویل نهایی {target_label}..."
                        )
                    else:
                        prog_text = (
                            f"📤 وضعیت آپلود ({target_label}):\n"
                            f"{bar} {pct}٪\n"
                            f"📊 ارسالی: {read_str} از {tot_str}"
                        )

                    # Send and record message_id asynchronously for later deletion
                    def _send_track(cid_val: str, msg_text: str):
                        ok_p, _, m_id = send_message_with_id(bot_token, cid_val, msg_text)
                        if ok_p and m_id:
                            progress_msg_tracker.append((cid_val, m_id))

                    threading.Thread(target=_send_track, args=(target_cid, prog_text), daemon=True).start()
                return _on_progress

            prog_cb = _create_part_progress_cb(part_num, total_parts, part["filename"])
            log_and_print(f"ارسال {part['filename']} (پارت {part_num}/{total_parts}{size_tag}) به {len(active_users)} کاربر...")
            results = broadcast_document(
                bot_token,
                active_users,
                part_path,
                caption=caption,
                log_callback=log_and_print,
                progress_callback=prog_cb
            )

            # Ensure all targeted users received this part successfully
            part_delivered_to_all = True
            for uid, (ok, msg) in results.items():
                if ok:
                    log_and_print(f"✅ پارت {part_num} به کاربر {uid} ارسال شد.")
                    if total_parts > 1:
                        send_message_async(bot_token, uid, f"✅ پارت {part_num} از {total_parts} با موفقیت تحویل داده شد.")
                else:
                    part_delivered_to_all = False
                    log_and_print(f"❌ ارسال پارت {part_num} به کاربر {uid} ناموفق بود: {msg}", "error")
                    send_message_async(bot_token, uid, f"⚠️ اختلال در تحویل پارت {part_num} از {total_parts}:\n{msg}")

            if not part_delivered_to_all or not results:
                all_parts_success = False
                if total_parts > 1:
                    log_and_print(f"⛔ پارت {part_num} با موفقیت ارسال نشد. به منظور جلوگیری از تحویل فایل ناقص و تکراری، ارسال سایر پارت‌ها متوقف گردید.", "warning")
                break

        if all_parts_success:
            record_sent_file(latest_file)
            log_and_print(f"✅ تمام پارت‌های «{file_name}» با موفقیت به همه کاربران ارسال و در تاریخچه ثبت شد.")

            # 3. Clean up temporary progress percentage messages from chat so chat remains tidy
            if progress_msg_tracker:
                log_and_print(f"🧹 در حال پاک‌سازی {len(progress_msg_tracker)} پیام درصد پیشرفت از چت بله...")
                delete_messages_async(bot_token, list(progress_msg_tracker))

            # 4. Final completion summary sent to all users in Bale
            completion_msg = (
                f"🎉 ارسال کامل فایل «{file_name}» با موفقیت انجام شد!\n\n"
                f"• نام فایل: {file_name}\n"
                f"• حجم فایل: {size_str}\n"
                f"• تعداد پارت‌ها: {total_parts} پارت ({part_size_mb}MB) تحویل داده شد.\n"
                f"• وضعیت سیستم: در حالت آماده‌باش و در انتظار فایل جدید بعدی"
            )
            broadcast_message(bot_token, active_users, completion_msg)

            # 5. Preserve source files on disk safely by default
            if config.get("delete_after_send", False):
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        log_and_print(f"🗑️ فایل اصلی «{file_name}» طبق تنظیمات با موفقیت از سیستم حذف گردید.")
                except Exception as del_err:
                    log_and_print(f"⚠️ عدم امکان حذف فایل: {del_err}", "warning")
            else:
                log_and_print(f"💾 فایل اصلی «{file_name}» با حفظ امنیت روی سیستم باقی ماند و ثبت شد.")

            return True
        else:
            log_and_print(f"⚠️ ارسال «{file_name}» به برخی کاربران یا پارت‌ها ناموفق بود. در دور بعدی مجدداً تلاش خواهد شد.", "warning")
            fail_msg = (
                f"⚠️ ارسال فایل «{file_name}» با اختلال شبکه مواجه شد.\n"
                f"سرویس پایش در چرخه بعدی مجدداً تلاش خواهد کرد."
            )
            broadcast_message_async(bot_token, active_users, fail_msg)
            return False

    except Exception as e:
        log_and_print(f"خطا در پردازش و ارسال فایل: {e}", "error")
        return False
    finally:
        if TEMP_DIR.exists():
            try:
                shutil.rmtree(TEMP_DIR)
            except Exception:
                pass

def perform_check():
    """Compatibility wrapper for tests and manual triggers."""
    return perform_send(log_if_duplicate=True)

def run_service_loop():
    """
    Main loop that runs continuously.
    - Continuously monitors folder for newly added or updated files.
    - Sends each file ONCE upon detection.
    - After sending, goes into idle waiting mode (does NOT repeatedly trigger send alarms).
    - Generates and logs a 5-minute deep status report every 5 minutes.
    - Manages the /start bot listener.
    """
    if not acquire_lock():
        sys.exit(0)

    log_and_print("=== سرویس پایش هوشمند فایل بله شروع به کار کرد (ارسال تک‌باره هر فایل و انتظار برای فایل جدید) ===")

    bot_listener: BaleBotListener = None
    current_token = ""

    last_report_epoch = time.time()
    last_folder_check = 0.0
    last_lic_log = 0.0
    last_alert_check = 0.0
    FOLDER_CHECK_INTERVAL = 3.0  # seconds between fast folder checks
    retry_after_epoch = 0.0      # backoff for retrying if sending failed

    # Initial folder check on startup
    try:
        init_cfg = load_config()
        init_raw_folder = init_cfg.get("folder_path", "").strip()
        is_valid, _, init_safe_path = validate_safe_folder(init_raw_folder)
        if is_valid:
            folder_str = str(init_safe_path)
            if not is_folder_baselined(folder_str):
                # First time configuring/monitoring this folder:
                # Baseline existing files so they are NOT sent. Wait for NEW files only!
                base_f = baseline_folder_contents(folder_str)
                if base_f:
                    log_and_print(f"📂 تنظیم اولیه پوشه: فایل‌های از قبل موجود (آخرین فایل: «{base_f['name']}») نادیده گرفته شدند. سیستم در انتظار فایل جدید بعدی قرار گرفت.")
                else:
                    log_and_print("📂 پوشه در حال حاضر خالی است. سیستم منتظر ورود اولین فایل جدید می‌باشد.")
            else:
                init_latest = get_latest_file(folder_str)
                if init_latest:
                    if is_file_already_sent(init_latest):
                        log_and_print(f"🟢 آخرین فایل موجود («{init_latest['name']}») قبلاً ثبت/ارسال شده است. سرویس در حالت انتظار برای فایل جدید قرار دارد.")
                    else:
                        log_and_print(f"🔔 فایل جدید ارسال‌نشده شناسایی شد: «{init_latest['name']}» - در حال ارسال...")
                        perform_send(log_if_duplicate=False)
                else:
                    log_and_print("📂 پوشه در حال حاضر خالی است. سرویس منتظر ورود اولین فایل می‌باشد.")
    except Exception as e:
        log_and_print(f"خطا در بررسی اولیه پوشه: {e}", "warning")

    try:
        while True:
            now = time.time()
            config = load_config()

            # License alert notifications (risk warnings during trial & post-expiration)
            if now - last_alert_check >= 60:
                try:
                    from core.license_notifier import check_and_send_license_alerts
                    check_and_send_license_alerts()
                except Exception:
                    pass
                last_alert_check = now

            # 0. License Verification
            lic_ok, lic_msg, _ = is_license_active()
            if not lic_ok:
                if now - last_lic_log >= 60:
                    log_and_print(f"🔒 {lic_msg} پایش و ارسال خودکار تا زمان فعال‌سازی متوقف است.", "warning")
                    last_lic_log = now
                time.sleep(2)
                continue

            # 1. Manage bot /start listener
            token = config.get("bot_token", "").strip()
            if token and token != current_token:
                if bot_listener:
                    bot_listener.stop()
                current_token = token
                bot_listener = BaleBotListener(current_token)
                bot_listener.start()
                log_and_print(f"شنونده استارت ربات برای توکن {mask_token(current_token)} فعال شد.")
                try:
                    check_and_notify_post_update(current_token)
                except Exception:
                    pass

            interval_mins = config.get("interval_minutes", 15)
            raw_folder = config.get("folder_path", "").strip()
            active_users = get_active_user_ids(config)

            # 2. Fast folder monitor: Detect and send NEW file once
            if now - last_folder_check >= FOLDER_CHECK_INTERVAL:
                last_folder_check = now
                if raw_folder and active_users and token and now >= retry_after_epoch:
                    is_valid, _, safe_path = validate_safe_folder(raw_folder)
                    if is_valid:
                        folder_str = str(safe_path)
                        if not is_folder_baselined(folder_str):
                            base_f = baseline_folder_contents(folder_str)
                            if base_f:
                                log_and_print(f"📂 تنظیم اولیه پوشه: فایل‌های از قبل موجود (آخرین فایل: «{base_f['name']}») نادیده گرفته شدند. سیستم در انتظار فایل جدید بعدی قرار گرفت.")
                        else:
                            latest_file = get_latest_file(folder_str)
                            # Only proceed if there is a file and it has NOT already been sent
                            if latest_file and not is_file_already_sent(latest_file):
                                log_and_print(f"🚀 فایل جدید شناسایی شد: «{latest_file['name']}» ({latest_file['readable_size']}) - در حال آماده‌سازی و ارسال...")
                                success = perform_send(log_if_duplicate=False)
                                if success:
                                    log_and_print(f"🟢 فایل «{latest_file['name']}» با موفقیت ارسال و ثبت شد. سیستم در انتظار فایل جدید بعدی قرار گرفت.")
                                    retry_after_epoch = 0.0
                                else:
                                    retry_after_epoch = now + 30.0
                                    log_and_print("⚠️ ارسال ناموفق بود. ۳۰ ثانیه دیگر مجدداً تلاش خواهد شد.", "warning")

            # 3. 5-minute deep status report
            if now - last_report_epoch >= REPORT_INTERVAL_SECONDS:
                report = generate_5min_status_report(
                    raw_folder,
                    len(active_users),
                    0.0,
                    interval_mins
                )
                log_and_print(report["report_text"])
                last_report_epoch = now

            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        log_and_print("سرویس توسط کاربر یا سیستم متوقف شد.")
    finally:
        if bot_listener:
            bot_listener.stop()
        release_lock()

if __name__ == "__main__":
    run_service_loop()
