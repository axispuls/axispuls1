import os
import json
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any

from .config_manager import get_base_dir, load_config, get_active_user_ids
from .security_utils import mask_token, atomic_write_json
from .bale_client import (
    BALE_BASE_URL,
    send_message,
    broadcast_message_async,
    answer_callback_query,
    send_document,
    download_file
)
from .ssl_helper import apply_ssl_fix
from .license_manager import SUPER_ADMIN_ID, is_license_active, activate_plan_directly, extend_license_days
from .hardware_info import collect_hardware_fingerprint, format_hardware_report
import shutil

REGISTERED_USERS_FILE = get_base_dir() / "registered_users.json"

def load_registered_users() -> List[Dict[str, Any]]:
    """Loads list of users who have started the bot."""
    if not REGISTERED_USERS_FILE.exists():
        return []
    try:
        with open(REGISTERED_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_registered_users(users: List[Dict[str, Any]]) -> bool:
    """Saves registered users to registered_users.json atomically."""
    try:
        content = json.dumps(users, ensure_ascii=False, indent=4)
        return atomic_write_json(REGISTERED_USERS_FILE, content)
    except Exception:
        return False

def record_user_start(user_id: int, first_name: str = "", username: str = "") -> None:
    """Records or updates a user who pressed /start."""
    users = load_registered_users()
    str_uid = str(user_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check if user already exists
    existing = next((u for u in users if str(u.get("user_id")) == str_uid), None)
    if existing:
        existing["last_seen"] = now_str
        existing["first_name"] = first_name
        existing["username"] = username
    else:
        users.insert(0, {
            "user_id": user_id,
            "first_name": first_name,
            "username": username,
            "started_at": now_str,
            "last_seen": now_str
        })
    save_registered_users(users[:100])

def build_welcome_message(user_id: int, first_name: str = "", is_known_user: bool = False) -> str:
    """
    Constructs the welcome and introduction message when a user sends /start.
    If the user is not in the system's authorized user list:
      - Delivers their numeric User ID prominently with 1-click copy monospace format.
      - Gives a comprehensive introduction to the Axis Puls software.
      - Explains that they can receive backup or critical system files immediately upon creation.
      - Provides @AXISPULS website/contact address.
      - Instructs them to enter the ID into the software if they are the owner, or introduces the system if they are a guest.
    If the user is already authorized:
      - Confirms active connection and readiness to receive automated files.
    """
    name_display = first_name.strip() if first_name else "کاربر گرامی"

    if not is_known_user:
        return (
            f"سلام {name_display} عزیز، به بازوی رسمی اکسیس پالس خوش آمدید! 🌸\n\n"
            f"🆔 شناسه عددی شما (User ID):\n"
            f"`{user_id}`\n"
            f"👆 (برای کپی آسان، روی عدد بالا کلیک یا لمس کنید)\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🌟 معرفی سامانه هوشمند اکسیس پالس (Axis Puls):\n"
            f"این ربات متصل به نرم‌افزار مانیتورینگ و ارسال خودکار «اکسیس پالس» است.\n"
            f"شما می‌توانید فایل‌های بکاپ، دیتابیس یا اسناد و فایل‌های مهم سیستم خود را بلافاصله پس از ایجاد شدن، به صورت خودکار، امن و بدون وقفه در پیام‌رسان بله دریافت نمایید.\n\n"
            f"⚡ امکانات کلیدی اکسیس پالس:\n"
            f"• پایش دائمی و ۲۴ ساعته پوشه‌های هدف در پس‌زمینه ویندوز\n"
            f"• ارسال قطعی و تک‌باره هر فایل پس از ایجاد، بدون حلقه تکرار\n"
            f"• فشرده‌سازی و تقسیم خودکار فایل‌های حجیم بالای ۲۰ مگابایت به پارت‌های زیپ استاندارد\n"
            f"• گزارش‌دهی خودکار وضعیت سیستم هر ۵ دقیقه\n\n"
            f"📌 راهنمای اتصال به سیستم:\n"
            f"• اگر شما مدیر یا مالک این سیستم هستید: شناسه عددی بالا را کپی کرده و در بخش «شناسه‌های ۳ کاربر» نرم‌افزار اکسیس پالس وارد نمایید تا دریافت فایل‌ها آغاز شود.\n"
            f"• اگر به عنوان کاربر متفرقه وارد شده‌اید: این سیستم جهت پایش و تحویل امن فایل‌های سیستمی طراحی شده است.\n\n"
            f"🌐 ارتباط با ما، صفحه اینستاگرام و سایت رسمی:\n"
            f"📸 instagram.com/axis_puls\n"
            f"💬 @AXISPULS"
        )
    else:
        return (
            f"سلام {name_display} عزیز! 🌸\n"
            f"شما به عنوان یکی از کاربران مجاز در سامانه اکسیس پالس (Axis Puls) ثبت شده‌اید.\n\n"
            f"🆔 شناسه عددی شما:\n"
            f"`{user_id}`\n\n"
            f"✅ وضعیت: متصل و آماده دریافت خودکار آخرین فایل‌های بکاپ و مهم سیستم.\n\n"
            f"🌐 ارتباط با پشتیبانی و اینستاگرام:\n"
            f"📸 instagram.com/axis_puls\n"
            f"💬 @AXISPULS"
        )

def get_admin_reply_keyboard() -> Dict[str, Any]:
    """Generates Reply Keyboard for Super Admin with large persistent quick-action buttons."""
    return {
        "keyboard": [
            [{"text": "📊 وضعیت سیستم"}, {"text": "🖥️ مشخصات سخت‌افزار"}],
            [{"text": "⭐ فعال‌سازی ۱ ساله"}, {"text": "💎 فعال‌سازی ۱۰ ساله"}],
            [{"text": "🎁 فعال‌سازی ۷۲ ساعته"}, {"text": "⏳ تمدید ۳۰ روزه"}],
            [{"text": "📤 ارسال آخرین نسخه"}, {"text": "📋 آخرین لاگ‌ها"}],
            [{"text": "👥 لیست کاربران"}, {"text": "🔄 ریست کامل سشن"}]
        ],
        "resize_keyboard": True
    }

def get_admin_inline_keyboard() -> Dict[str, Any]:
    """Generates Inline Keyboard attached beneath messages for instant click execution."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 وضعیت سیستم", "callback_data": "cmd_status"},
                {"text": "🖥️ مشخصات قطعات", "callback_data": "cmd_hardware"}
            ],
            [
                {"text": "⭐ فعال‌سازی ۱ ساله", "callback_data": "cmd_act_1y"},
                {"text": "💎 فعال‌سازی ۱۰ ساله", "callback_data": "cmd_act_10y"}
            ],
            [
                {"text": "🎁 فعال‌سازی ۷۲ ساعته", "callback_data": "cmd_act_72h"},
                {"text": "⏳ تمدید ۳۰ روزه", "callback_data": "cmd_ext_30"}
            ],
            [
                {"text": "📤 ارسال آخرین نسخه", "callback_data": "cmd_send_update"},
                {"text": "📋 لاگ‌های اخیر", "callback_data": "cmd_logs"}
            ],
            [
                {"text": "👥 لیست کاربران", "callback_data": "cmd_users"},
                {"text": "🔄 ریست سشن (شروع از صفر)", "callback_data": "cmd_reset_session"}
            ]
        ]
    }

class BaleBotListener:
    """
    Background worker that listens for /start commands from users,
    replies with their numeric user ID, and records them.
    """
    def __init__(self, bot_token: str, on_user_start: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.bot_token = bot_token.strip()
        self.on_user_start = on_user_start
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_update_id = 0

    def start(self):
        """Starts the long-polling listener thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_poll_loop, daemon=True, name="BaleBotListener")
        self._thread.start()

    def stop(self):
        """Stops the listener thread cleanly."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_poll_loop(self):
        token = self.bot_token
        if not token:
            return

        while not self._stop_event.is_set():
            try:
                url = f"{BALE_BASE_URL}{token}/getUpdates"
                params = {
                    "offset": self.last_update_id + 1,
                    "timeout": 15
                }
                ca_bundle = apply_ssl_fix()
                response = requests.get(url, params=params, timeout=25, verify=ca_bundle)
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        data = {}
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            up_id = update.get("update_id", 0)
                            if up_id > self.last_update_id:
                                self.last_update_id = up_id

                            self._process_single_update(update)
                elif response.status_code in (401, 404):
                    # Invalid token, wait longer before retrying
                    time.sleep(10)
                else:
                    time.sleep(3)
            except requests.exceptions.RequestException:
                time.sleep(4)
            except Exception:
                time.sleep(3)

    def _process_single_update(self, update: Dict[str, Any]):
        """
        Inspects an update.
        Handles both text messages and callback_query (inline button clicks).
        If sender is SUPER_ADMIN_ID (1147503382):
            Processes remote administrative commands with full button support.
        Otherwise:
            If text starts with /start, replies with user's numeric ID and system introduction.
        """
        # 1. Handle Inline Button Clicks (callback_query)
        callback_query = update.get("callback_query")
        if callback_query:
            from_user = callback_query.get("from", {})
            user_id = from_user.get("id")
            cq_id = callback_query.get("id", "")
            data = str(callback_query.get("data", "")).strip()

            if user_id == SUPER_ADMIN_ID or str(user_id) == str(SUPER_ADMIN_ID):
                try:
                    answer_callback_query(self.bot_token, cq_id)
                except Exception:
                    pass

                cmd_map = {
                    "cmd_status": "/status",
                    "cmd_hardware": "/hardware",
                    "cmd_act_1y": "/activate 1y",
                    "cmd_act_10y": "/activate 10y",
                    "cmd_act_72h": "/activate 72h",
                    "cmd_ext_30": "/extend 30",
                    "cmd_send_update": "/update",
                    "cmd_apply_github_update": "/update_github_now",
                    "cmd_download_current_exe": "/send_setup_to_me",
                    "cmd_logs": "/logs",
                    "cmd_users": "/users",
                    "cmd_reset_session": "/reset",
                    "cmd_menu": "/start"
                }
                text_cmd = cmd_map.get(data, "/start")
                self._handle_admin_message(text_cmd, user_id, from_user)
            return

        message = update.get("message")
        if not message:
            return

        text = (message.get("text") or message.get("caption") or "").strip()
        from_user = message.get("from", {})
        user_id = from_user.get("id")
        first_name = from_user.get("first_name", "")
        username = from_user.get("username", "")

        if not user_id:
            return

        # 2. Super Admin Remote Control Handling
        if user_id == SUPER_ADMIN_ID or str(user_id) == str(SUPER_ADMIN_ID):
            doc = message.get("document")
            if doc:
                self._handle_admin_incoming_document(doc, user_id, from_user)
                return
            self._handle_admin_message(text, user_id, from_user)
            return

        # 3. Regular User Start Handling
        if text.startswith("/start"):
            # Record user
            record_user_start(user_id, first_name, username)

            # Check if user is configured in active users list
            is_known = False
            try:
                cfg = load_config()
                active_ids = [str(u).strip() for u in get_active_user_ids(cfg) if u]
                is_known = str(user_id).strip() in active_ids
            except Exception:
                pass

            # Reply to user
            reply_text = build_welcome_message(user_id, first_name, is_known_user=is_known)
            send_message(self.bot_token, str(user_id), reply_text)

            # Trigger callback if registered
            if self.on_user_start:
                try:
                    self.on_user_start({
                        "user_id": user_id,
                        "first_name": first_name,
                        "username": username,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                except Exception:
                    pass

    def _handle_admin_message(self, text: str, user_id: int, from_user: Dict[str, Any]):
        """Processes remote control and license management commands from Super Admin."""
        cmd = text.strip()

        # Map Persian Reply Keyboard button clicks to commands
        if "۱ ساله" in cmd or "1 ساله" in cmd or "یکساله" in cmd:
            cmd = "/activate 1y"
        elif "۱۰ ساله" in cmd or "10 ساله" in cmd or "ده‌ساله" in cmd:
            cmd = "/activate 10y"
        elif "۷۲ ساعته" in cmd or "72 ساعته" in cmd:
            cmd = "/activate 72h"
        elif "تمدید ۳۰" in cmd or "تمدید 30" in cmd:
            cmd = "/extend 30"
        elif "آخرین نسخه" in cmd or "ارسال آخرین نسخه" in cmd or "نسخه جدید" in cmd:
            cmd = "/update"
        elif "سخت‌افزار" in cmd or "سخت افزار" in cmd or "قطعات" in cmd:
            cmd = "/hardware"
        elif "وضعیت" in cmd:
            cmd = "/status"
        elif "لاگ" in cmd:
            cmd = "/logs"
        elif "کاربران" in cmd:
            cmd = "/users"

        cmd_lower = cmd.lower()
        first_word = cmd.split()[0].lower() if cmd else ""

        # A. Help / Start Menu
        if cmd_lower in ("/start", "/help", "/menu", "راهنما", "شروع", "منو"):
            help_msg = (
                f"👑 سلام مدیر گرامی (شناسه: `{SUPER_ADMIN_ID}`)\n"
                f"به پنل هوشمند مدیریت از راه دور «اکسیس پالس» خوش آمدید! 🌸\n\n"
                f"📱 جهت سرعت و آسودگی شما، **دکمه‌های لمسی کنترلی** زیر فعال شدند.\n"
                f"می‌توانید با فشردن هر یک از دکمه‌های پایین صفحه یا دکمه‌های زیر، عملکرد سیستم را بدون نیاز به تایپ دستی مدیریت نمایید:"
            )
            # Send message with persistent Reply Keyboard at bottom
            send_message(
                self.bot_token,
                str(user_id),
                help_msg,
                reply_markup=get_admin_reply_keyboard()
            )
            # Send quick action inline buttons directly attached
            send_message(
                self.bot_token,
                str(user_id),
                "⚡ منوی دسترسی سریع (دکمه‌های شیشه‌ای):",
                reply_markup=get_admin_inline_keyboard()
            )
            return

        # B. Status
        if cmd_lower in ("/status", "/وضعیت", "وضعیت"):
            lic_ok, lic_msg, lic_info = is_license_active()
            cfg = load_config()
            folder = cfg.get("folder_path", "مشخص نشده")

            drive = folder[:2] if folder and len(folder) >= 2 else "C:"
            total_gb, free_gb = 0, 0
            try:
                usage = shutil.disk_usage(drive)
                total_gb = round(usage.total / (1024 ** 3), 1)
                free_gb = round(usage.free / (1024 ** 3), 1)
            except Exception:
                pass

            from .state_manager import load_state
            state = load_state()
            processed_count = len(state.get("processed_files", {}))
            last_file = state.get("last_processed_file", "هنوز فایلی ارسال نشده")

            status_msg = (
                f"📊 گزارش وضعیت لحظه‌ای نرم‌افزار اکسیس پالس:\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔒 وضعیت مجوز: {'✅ فعال و معتبر' if lic_ok else '❌ غیرفعال یا منقضی'}\n"
                f"• عنوان پلن: {lic_info.get('plan_title', 'تعریف‌نشده')}\n"
                f"• اعتبار باقیمانده: {lic_info.get('time_rem_str', 'منقضی')}\n"
                f"• تاریخ انقضا: {lic_info.get('expiry_str', '-')}\n\n"
                f"📁 پوشه پایش فایل: `{folder}`\n"
                f"💾 وضعیت حافظه ({drive}): {free_gb} GB آزاد از {total_gb} GB\n"
                f"📦 تعداد کل فایل‌های ارسال‌شده: {processed_count} فایل\n"
                f"🕒 آخرین فایل پردازش‌شده: `{last_file}`\n"
                f"⏱️ فاصله بررسی خودکار: هر {cfg.get('interval_minutes', 5)} دقیقه"
            )
            send_message(
                self.bot_token,
                str(user_id),
                status_msg,
                reply_markup=get_admin_reply_keyboard()
            )
            return

        # C. Hardware Info (For verifying OS Reinstall claims)
        if cmd_lower in ("/hardware", "/info", "/sys", "/سخت_افزار", "سخت افزار", "سیستم"):
            hw = collect_hardware_fingerprint()
            report = format_hardware_report(hw)
            send_message(
                self.bot_token,
                str(user_id),
                report,
                reply_markup=get_admin_reply_keyboard()
            )
            return

        # D. Activate Plan Remotely
        if first_word in ("/activate", "/فعالسازی", "فعالسازی"):
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                send_message(self.bot_token, str(user_id), "⚠️ لطفاً نوع پلن یا تعداد روز را مشخص کنید.\nمثال:\n`/activate 72h`\n`/activate 1y`\n`/activate 10y`\n`/activate 30`", reply_markup=get_admin_reply_keyboard())
                return

            arg = parts[1].strip().lower()
            plan_id = "trial_72h"
            custom_days = None

            if arg in ("72h", "trial", "3d", "3", "رایگان", "آزمایشی"):
                plan_id = "trial_72h"
            elif arg in ("1y", "1year", "1_year", "365", "یک‌ساله", "یکساله", "1"):
                plan_id = "plan_1y"
            elif arg in ("10y", "10year", "10_year", "3650", "ده‌ساله", "دهساله", "10"):
                plan_id = "plan_10y"
            elif arg.isdigit() and int(arg) > 0:
                custom_days = int(arg)
                plan_id = "custom"
            else:
                send_message(self.bot_token, str(user_id), f"⚠️ پلن «{arg}» شناسایی نشد.\nمقادیر معتبر: `72h`، `1y`، `10y` یا تعداد روز مانند `30`، `60`، `90`", reply_markup=get_admin_reply_keyboard())
                return

            ok, msg, lic_data = activate_plan_directly(plan_id, custom_days=custom_days, activated_by=f"admin_{user_id}")
            if ok:
                plan_title = lic_data.get("plan_title", "")
                exp_str = lic_data.get("expires_at_str", "")
                resp = (
                    f"✅ مجوز نرم‌افزار کلاینت با موفقیت فعال گردید!\n\n"
                    f"• نوع پلن: {plan_title}\n"
                    f"• تاریخ انقضا: {exp_str}\n"
                    f"• شناسه فعال‌کننده: مدیر ارشد ({user_id})\n\n"
                    f"سیستم کلاینت هم‌اکنون به صورت کامل فعال و عملیاتی است."
                )
                send_message(self.bot_token, str(user_id), resp, reply_markup=get_admin_reply_keyboard())

                # Notify client active users
                try:
                    cfg = load_config()
                    uids = get_active_user_ids(cfg)
                    user_alert = (
                        f"🎉 کاربر گرامی، مجوز استفاده از سامانه اکسیس پالس سیستم شما توسط مدیر فعال/تمدید گردید!\n"
                        f"• نوع مجوز: {plan_title}\n"
                        f"• تاریخ اعتبار: تا {exp_str}\n"
                        f"سیستم آماده ارسال سریع و خودکار فایل‌های شما در بله می‌باشد."
                    )
                    broadcast_message_async(self.bot_token, uids, user_alert)
                except Exception:
                    pass
            else:
                send_message(self.bot_token, str(user_id), f"❌ خطا در فعال‌سازی مجوز: {msg}", reply_markup=get_admin_reply_keyboard())
            return

        # E. Extend License Days
        if first_word in ("/extend", "/تمدید", "تمدید"):
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                send_message(self.bot_token, str(user_id), "⚠️ لطفاً تعداد روزهای تمدید را به عدد مشخص کنید.\nمثال: `/extend 30` (جهت افزودن ۳۰ روز به اعتبار فعلی)", reply_markup=get_admin_reply_keyboard())
                return

            add_days = int(parts[1].strip())
            ok, msg, lic_data = extend_license_days(add_days, activated_by=f"admin_{user_id}")
            if ok:
                plan_title = lic_data.get("plan_title", "")
                exp_str = lic_data.get("expires_at_str", "")
                resp = (
                    f"✅ لایسنس سیستم با موفقیت به مدت {add_days} روز تمدید شد!\n\n"
                    f"• وضعیت جدید: {plan_title}\n"
                    f"• تاریخ جدید انقضا: {exp_str}\n"
                    f"• شناسه اعمال: مدیر ارشد ({user_id})"
                )
                send_message(self.bot_token, str(user_id), resp, reply_markup=get_admin_reply_keyboard())

                # Notify client active users
                try:
                    cfg = load_config()
                    uids = get_active_user_ids(cfg)
                    user_alert = (
                        f"🎉 کاربر گرامی، اعتبار نرم‌افزار سیستم شما به مدت {add_days} روز توسط مدیر تمدید شد.\n"
                        f"• تاریخ انقضای جدید: {exp_str}"
                    )
                    broadcast_message_async(self.bot_token, uids, user_alert)
                except Exception:
                    pass
            else:
                send_message(self.bot_token, str(user_id), f"❌ خطا در تمدید لایسنس: {msg}", reply_markup=get_admin_reply_keyboard())
            return

        # F. View Recent Logs
        if cmd_lower in ("/logs", "/لاگ", "لاگ"):
            log_file = get_base_dir() / "service.log"
            if not log_file.exists():
                send_message(self.bot_token, str(user_id), "ℹ️ هنوز هیچ فایل لاگی ثبت نشده است.", reply_markup=get_admin_reply_keyboard())
                return
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                last_lines = lines[-15:] if len(lines) > 15 else lines
                content = "".join(last_lines).strip()
                if not content:
                    content = "(فایل لاگ خالی است)"
                msg = f"📋 آخرین لاگ‌های عملکرد سیستم کلاینت:\n\n```text\n{content}\n```"
                send_message(self.bot_token, str(user_id), msg, reply_markup=get_admin_reply_keyboard())
            except Exception as e:
                send_message(self.bot_token, str(user_id), f"❌ خطا در خواندن فایل لاگ: {e}", reply_markup=get_admin_reply_keyboard())
            return

        # G. View Users
        if cmd_lower in ("/users", "/کاربران", "کاربران"):
            cfg = load_config()
            cfg_users = get_active_user_ids(cfg)
            reg_users = load_registered_users()

            cfg_str = "\n".join([f"  • `{u}`" for u in cfg_users]) if cfg_users else "  (هیچ کاربری در تنظیمات ست نشده)"
            reg_str = ""
            for idx, r in enumerate(reg_users[:10], 1):
                name = r.get("first_name", "") or r.get("username", "")
                reg_str += f"  {idx}. `{r.get('user_id')}` ({name}) - آخرین حضور: {r.get('last_seen', '-')}\n"
            if not reg_str:
                reg_str = "  (هیچ کاربری بات را استارت نکرده)"

            msg = (
                f"👥 کاربران ثبت‌شده در سیستم:\n\n"
                f"📌 شناسه‌های مجاز در تنظیمات نرم‌افزار:\n{cfg_str}\n\n"
                f"🤖 آخرین کاربرانی که بات را استارت کرده‌اند:\n{reg_str}"
            )
            send_message(self.bot_token, str(user_id), msg, reply_markup=get_admin_reply_keyboard())
            return

        # H. Remote Update Prompt & Setup Handler
        if cmd_lower in ("/update_github_now", "/install_update"):
            self._handle_admin_apply_github_update(user_id)
            return

        if cmd_lower in ("/update", "/upgrade", "/نسخه", "ارسال آخرین نسخه", "بررسی به‌روزرسانی") or first_word in ("/update", "/upgrade"):
            self._handle_admin_update_prompt(user_id)
            return

        if cmd_lower in ("/send_setup_to_me", "/get_setup", "دریافت ستاپ"):
            self._handle_admin_send_setup_to_me(user_id)
            return

        # I. Reset Session (Wipes license, session, and returns software to initial install state)
        if cmd_lower in ("/reset", "/reset_session", "ریست", "ریست سشن", "ریست کامل سشن", "🔄 ریست کامل سشن"):
            from .license_manager import reset_software_session
            ok, msg = reset_software_session()
            if ok:
                resp = (
                    "🔄 **سشن و دیتای نرم‌افزار کلاینت با موفقیت ریست شد!**\n\n"
                    "• تمامی مجوزها، اطلاعات سشن، هشدارهای انقضا و سوابق پاک شدند.\n"
                    "• این نرم‌افزار هم‌اکنون به حالت اولیه (روز اول نصب) بازگشته و در اجرای بعدی، از کاربر درخواست فعال‌سازی خواهد کرد."
                )
            else:
                resp = f"⚠️ خطا در ریست سشن: {msg}"
            send_message(self.bot_token, str(user_id), resp, reply_markup=get_admin_reply_keyboard())
            return

        # Default fallback for admin
        send_message(
            self.bot_token,
            str(user_id),
            "دستور یا کلید نامعتبر است. لطفاً از دکمه‌های زیر استفاده فرمایید.",
            reply_markup=get_admin_reply_keyboard()
        )

    def _handle_admin_update_prompt(self, user_id: int):
        """Displays update instructions and options to Super Admin, checking GitHub releases."""
        import socket, platform
        from .self_updater import get_current_executable_path
        from .version import get_current_version
        from .github_updater import check_for_github_update

        cur_exe = get_current_executable_path()
        cur_ver = get_current_version()
        sys_name = socket.gethostname()
        os_name = f"{platform.system()} {platform.release()}"

        try:
            gh_info = check_for_github_update()
        except Exception as e:
            gh_info = {"ok": False, "error": str(e)}

        has_gh = gh_info.get("ok", False)
        latest_ver = gh_info.get("latest_version", "نامشخص")
        size_mb = gh_info.get("asset_size_mb", 0)
        notes = gh_info.get("notes", "بهبود کارایی و پایداری سیستم")
        published_at = gh_info.get("published_at", "")
        if published_at:
            published_at = published_at.replace("T", " ").replace("Z", " UTC")
        else:
            published_at = "ثبت‌شده"

        buttons = []

        if has_gh:
            has_update = gh_info.get("has_update", False)
            if has_update:
                status_header = "🌟 **نسخه جدیدتر در گیت‌هاب موجود است!**"
                btn_action_text = f"🚀 دانلود و ارتقا به نسخه {latest_ver}"
            else:
                status_header = "✅ **نرم‌افزار شما با نسخه گیت‌هاب همگام است.**"
                btn_action_text = f"🔄 دانلود و نصب مجدد نسخه {latest_ver}"

            detail_section = (
                f"{status_header}\n\n"
                f"📊 **مقایسه نسخه‌ها و اطلاعات انتشار:**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🖥️ **نسخه فعلی این سیستم:** `v{cur_ver}`\n"
                f"🌐 **آخرین نسخه در گیت‌هاب:** `{latest_ver}`\n"
                f"📦 **حجم فایل ستاپ در گیت‌هاب:** `{size_mb} MB`\n"
                f"🕒 **تاریخ انتشار نسخه:** `{published_at}`\n"
                f"📝 **توضیحات و تغییرات:**\n{notes}\n\n"
                f"👇 برای دریافت و نصب آخرین نسخه روی دکمه زیر کلیک فرمایید:"
            )
            # Always provide the update/reinstall button so the user can update whenever they wish!
            buttons.append([{"text": btn_action_text, "callback_data": "cmd_apply_github_update"}])
            buttons.append([{"text": "🔄 بررسی مجدد گیت‌هاب", "callback_data": "cmd_send_update"}])
        else:
            err_msg = gh_info.get("error", "عدم دسترسی به مخزن")
            detail_section = (
                f"⚠️ **وضعیت استعلام از گیت‌هاب:** {err_msg}\n\n"
                f"🖥️ **نسخه فعلی سیستم:** `v{cur_ver}`\n"
                f"💡 برای تلاش مجدد یا ارسال فایل دستی از دکمه‌های زیر استفاده فرمایید."
            )
            buttons.append([{"text": "🔄 تلاش مجدد برای بررسی گیت‌هاب", "callback_data": "cmd_send_update"}])

        buttons.append([{"text": "📥 ارسال فایل ستاپ این سیستم برای من", "callback_data": "cmd_download_current_exe"}])
        buttons.append([{"text": "📊 وضعیت سیستم", "callback_data": "cmd_status"}])

        msg = (
            f"🚀 **سامانه استعلام و به‌روزرسانی خودکار نرم‌افزار**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ **سیستم کلاینت:** `{sys_name}` ({os_name})\n"
            f"📁 **مسیر فایل اجرایی فعال:** `{cur_exe}`\n\n"
            f"{detail_section}\n\n"
            f"💡 **روش جایگزین دستی:**\n"
            f"همچنین می‌توانید فایل ستاپ جدید (`AxisPuls_Setup.exe`) را مستقیماً به عنوان فایل در همین چت ارسال نمایید."
        )

        send_message(self.bot_token, str(user_id), msg, reply_markup={"inline_keyboard": buttons})

    def _handle_admin_apply_github_update(self, user_id: int):
        """Downloads the latest release directly from GitHub and performs automated self-update."""
        import threading
        from .github_updater import check_for_github_update, download_github_release_asset
        from .self_updater import apply_update_and_restart, UPDATE_DIR

        def _do_update():
            gh_info = check_for_github_update()
            if not gh_info.get("ok"):
                send_message(self.bot_token, str(user_id), f"❌ خطا در دریافت اطلاعات نسخه از گیت‌هاب: {gh_info.get('error')}", reply_markup=get_admin_reply_keyboard())
                return

            download_url = gh_info.get("download_url")
            if not download_url:
                send_message(self.bot_token, str(user_id), "❌ لینک دانلود فایل ستاپ در انتشار گیت‌هاب یافت نشد.", reply_markup=get_admin_reply_keyboard())
                return

            latest_ver = gh_info.get("latest_version", "latest")
            size_mb = gh_info.get("asset_size_mb", 0)

            send_message(
                self.bot_token,
                str(user_id),
                f"⏳ در حال دانلود نسخه جدید (`{latest_ver}`) با حجم `{size_mb} MB` از گیت‌هاب...\nلطفاً تا اتمام دانلود و ریستارت خودکار صبور باشید.",
                reply_markup=get_admin_reply_keyboard()
            )

            UPDATE_DIR.mkdir(parents=True, exist_ok=True)
            target_file = UPDATE_DIR / f"AxisPuls_Setup_{latest_ver}.exe"

            ok, dmsg = download_github_release_asset(download_url, target_file)
            if not ok:
                send_message(self.bot_token, str(user_id), f"❌ دانلود ناموفق بود: {dmsg}", reply_markup=get_admin_reply_keyboard())
                return

            send_message(self.bot_token, str(user_id), "✅ دانلود کامل شد. در حال بستن سرویس‌های قبلی و جایگزینی فایل...")

            res_ok, res_msg = apply_update_and_restart(target_file)
            if not res_ok:
                send_message(self.bot_token, str(user_id), f"❌ خطا در اعمال به‌روزرسانی: {res_msg}", reply_markup=get_admin_reply_keyboard())

        threading.Thread(target=_do_update, daemon=True).start()

    def _handle_admin_send_setup_to_me(self, user_id: int):
        """Sends the current AxisPuls_Setup.exe executable to Super Admin via Bale using safe multi-part splitting."""
        from .setup_sender import send_application_setup
        send_message(
            self.bot_token,
            str(user_id),
            "⏳ در حال آماده‌سازی و ارسال آخرین نسخه نرم‌افزار (در قالب پارت‌های امن زیر ۲۰ مگابایت)...",
            reply_markup=get_admin_reply_keyboard()
        )
        ok, res = send_application_setup(self.bot_token, [str(user_id)])
        if not ok:
            send_message(
                self.bot_token,
                str(user_id),
                f"❌ خطا در فرآیند ارسال ستاپ: {res}",
                reply_markup=get_admin_reply_keyboard()
            )

    def _handle_admin_incoming_document(self, document: Dict[str, Any], user_id: int, from_user: Dict[str, Any]):
        """
        Receives an uploaded executable or zip package from Super Admin and initiates automated self-update.
        Supports single .exe, .zip archives, and sequential multi-part (.zip.001, .zip.002, ...) updates.
        """
        file_id = document.get("file_id")
        file_name = document.get("file_name", "AxisPuls_Setup.exe")
        file_size = document.get("file_size", 0)
        size_mb = round(file_size / (1024 * 1024), 2)

        if not file_id:
            send_message(self.bot_token, str(user_id), "❌ شناسه فایل (file_id) نامعتبر است.", reply_markup=get_admin_reply_keyboard())
            return

        send_message(
            self.bot_token,
            str(user_id),
            f"📥 **دریافت فایل نسخه جدید از مدیر:**\n"
            f"• نام فایل: `{file_name}`\n"
            f"• حجم فایل: {size_mb} مگابایت\n\n"
            f"⏳ در حال دانلود و اعتبارسنجی فایل در سیستم کلاینت...",
            reply_markup=get_admin_reply_keyboard()
        )

        from .self_updater import UPDATE_DIR, apply_update_and_restart
        from .archiver import extract_executable_from_zip, reassemble_split_parts
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = UPDATE_DIR / f"staged_{file_name}"

        ok, msg = download_file(self.bot_token, file_id, str(dest_path))
        if not ok:
            send_message(
                self.bot_token,
                str(user_id),
                f"❌ خطا در دانلود فایل نسخه جدید:\n{msg}",
                reply_markup=get_admin_reply_keyboard()
            )
            return

        target_exe_to_apply = None

        # Case 1: Multi-part archive (.zip.001, .zip.002, or .001, .002)
        lower_name = file_name.lower()
        if any(lower_name.endswith(f".{i:03d}") for i in range(1, 100)):
            parts_dir = UPDATE_DIR / "incoming_parts"
            parts_dir.mkdir(parents=True, exist_ok=True)
            saved_part = parts_dir / file_name
            if dest_path.exists():
                if saved_part.exists():
                    saved_part.unlink()
                dest_path.rename(saved_part)

            # Discover all parts matching this base prefix
            base_prefix = file_name.rsplit(".", 1)[0]
            existing_parts = sorted(list(parts_dir.glob(f"{base_prefix}.*")))
            part_numbers = []
            for p in existing_parts:
                try:
                    part_numbers.append(int(p.suffix.lstrip(".")))
                except Exception:
                    pass

            send_message(
                self.bot_token,
                str(user_id),
                f"🧩 **پارت دریافتی ذخیره شد:** `{file_name}`\n"
                f"📊 پارت‌های موجود تاکنون: {len(existing_parts)} پارت\n"
                f"💡 در صورت وجود پارت‌های بعدی، آن‌ها را نیز ارسال فرمایید.",
                reply_markup=get_admin_reply_keyboard()
            )

            # Check if sequential starting from 1: [1, 2, ..., N]
            if part_numbers and part_numbers == list(range(1, len(part_numbers) + 1)):
                # Attempt to reassemble and test if it's a complete valid archive
                assembled_zip = UPDATE_DIR / f"assembled_{base_prefix}"
                reassemble_split_parts([str(p) for p in existing_parts], str(assembled_zip))
                extracted_exe = extract_executable_from_zip(str(assembled_zip), str(UPDATE_DIR))
                if extracted_exe and Path(extracted_exe).exists():
                    target_exe_to_apply = Path(extracted_exe)
                    send_message(
                        self.bot_token,
                        str(user_id),
                        f"✅ تمامی {len(existing_parts)} پارت با موفقیت تجمیع و فایل اجرایی استخراج شد!\n"
                        f"🔄 در حال آغاز عملیات جایگزینی خودکار...",
                        reply_markup=get_admin_reply_keyboard()
                    )

        # Case 2: Zip archive containing .exe
        elif lower_name.endswith(".zip"):
            extracted_exe = extract_executable_from_zip(str(dest_path), str(UPDATE_DIR))
            if extracted_exe and Path(extracted_exe).exists():
                target_exe_to_apply = Path(extracted_exe)
            else:
                send_message(
                    self.bot_token,
                    str(user_id),
                    "❌ فایل زیپ دانلود شد اما هیچ فایل اجرایی (.exe) معتبری داخل آن یافت نشد.",
                    reply_markup=get_admin_reply_keyboard()
                )
                return

        # Case 3: Direct executable (.exe)
        elif lower_name.endswith(".exe"):
            target_exe_to_apply = dest_path

        else:
            send_message(
                self.bot_token,
                str(user_id),
                f"⚠️ فرمت فایل ناشناخته است (`{file_name}`). لطفاً فایل با پسوند `.exe`، `.zip` یا پارت‌های `.zip.001` ارسال فرمایید.",
                reply_markup=get_admin_reply_keyboard()
            )
            return

        if target_exe_to_apply:
            size_tag = ""
            try:
                if target_exe_to_apply.exists():
                    size_tag = f" ({round(target_exe_to_apply.stat().st_size / (1024*1024), 2)} MB)"
            except Exception:
                pass

            send_message(
                self.bot_token,
                str(user_id),
                f"✅ فایل اجرایی نسخه جدید آماده شد{size_tag}.\n"
                f"🔄 در حال آغاز جایگزینی خودکار و راه‌اندازی مجدد با آخرین نسخه...",
                reply_markup=get_admin_reply_keyboard()
            )
            up_ok, up_msg = apply_update_and_restart(target_exe_to_apply)
            if not up_ok:
                send_message(
                    self.bot_token,
                    str(user_id),
                    f"❌ خطا در اجرای فرآیند به‌روزرسانی:\n{up_msg}",
                    reply_markup=get_admin_reply_keyboard()
                )
