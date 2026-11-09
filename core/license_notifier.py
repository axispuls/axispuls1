"""
License Expiration & Data Protection Notifier for Axis Puls.
Manages automated urgent notifications regarding license expiration,
unbacked data risks, and renewal instructions via Bale Messenger.
"""

import json
import time
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from .bale_client import send_message, broadcast_message_async
from .config_manager import load_config, get_base_dir
from .license_manager import is_license_active, SUPER_ADMIN_ID, SUPER_ADMIN_ID_STR, PLANS

logger = logging.getLogger("LicenseNotifier")

SUPPORT_BALE_ID = "@AXISPULS"
SUPPORT_PHONE = "09922975101"
ALERT_STATE_FILE = get_base_dir() / "expiration_alert_state.json"

# --- Rotating Alert Message Templates ---

TRIAL_DANGER_TEMPLATES = [
    (
        "🚨 **اخطار امنیتی: وضعیت قرمز اطلاعات و عدم وجود بکاپ**\n\n"
        "کاربر گرامی، بیش از ۲۴ ساعت از فعال‌سازی نسخه آزمایشی گذشته است.\n"
        "⚠️ **توجه بسیار مهم:** اطلاعات سیستم شما بدون هیچ‌گونه فایل پشتیبان (بکاپ) ذخیره می‌شود "
        "و هر لحظه در صورت اتمام زمان، ریسک پاک‌سازی قطعی دیتابیس و نابودی اطلاعات وجود دارد!\n\n"
        "برای اتصال به سرور بکاپ امن و جلوگیری از نابودی اطلاعات، سریعاً به پشتیبانی پیام دهید:\n"
        f"💬 پشتیبانی بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس پشتیبانی: `{SUPPORT_PHONE}`"
    ),
    (
        "⚠️ **هشدار بحرانی دیتابیس: اطلاعات شما در خطر نابودی قرار دارد!**\n\n"
        "دوره آزمایشی فاقد گارانتی نگهداری داده است. با به پایان رسیدن تایمر اعتبار، داده‌ها و تاریخچه سیستم "
        "فوراً از دسترس خارج شده و غیرقابل بازگردانی خواهند بود.\n\n"
        "سریعاً جهت فعال‌سازی لایسنس دائم و ثبت بکاپ به پشتیبانی پیام دهید:\n"
        f"💬 ارتباط با پشتیبانی: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "⛔ **اخطار قطعی: شمارش معکوس تخریب حافظه موقت**\n\n"
        "سیستم شما در حال حاضر روی مخزن موقت کار می‌کند. در صورت عدم تمدید پیش از صفر شدن زمان، "
        "کلیه فایل‌ها و تنظیمات پردازش‌شده بازنویسی و پاک خواهند شد.\n\n"
        "تا دیر نشده و اطلاعات شما نسوخته است، اکانت خود را تمدید کنید:\n"
        f"💬 اکانت پشتیبانی در بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🔥 **هشدار ریسک بالای از دست رفتن فایل‌ها و داده‌ها**\n\n"
        "یادآوری مهم: دیتابیس شما در وضعیت موقت (Unsafe Storage) قرار دارد. "
        "کوچک‌ترین اختلال یا پایان مهلت اشتراک منجر به حذف همیشگی داده‌ها خواهد شد.\n\n"
        "همین حالا پیام دهید تا اکانت شما تمدید و داده‌ها بیمه شوند:\n"
        f"💬 پشتیبانی سریع در بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🛑 **اعلان اضطراری سرور: آماده‌سازی تخلیه دیتای بدون لایسنس**\n\n"
        "پرونده شما در صف حساب‌های بدون پشتیبان قرار گرفته است. "
        "به محض اتمام مهلت ۷۲ ساعته، هیچ فرصتی برای استخراج یا بازگردانی فایل‌ها نخواهد بود.\n\n"
        "تمدید فوری از طریق پشتیبانی:\n"
        f"💬 پشتیبانی بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    )
]

EXPIRED_IMMEDIATE_TEMPLATES = [
    (
        "🛑 **حساب شما منقضی شد - آغاز شمارش معکوس پاک‌سازی کامل اطلاعات!**\n\n"
        "اعتبار لایسنس شما به پایان رسید و کلیه خدمات مانیتور و ارسال متوقف گردید.\n"
        "داده‌های شما وارد صف حذف دائم شده‌اند و ظرف ساعات آینده به طور برگشت‌ناپذیر پاک خواهند شد!\n\n"
        "برای نجات فوری اطلاعات و تمدید اکانت، سریعاً پیام دهید:\n"
        f"💬 پشتیبانی بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🚨 **وضعیت اضطراری: تعلیق سرور و اخطار امحای دیتای ذخیره نشده**\n\n"
        "اشتراک شما تمام شده است! سرور در حال آزادسازی حافظه موقت است و اطلاعات شما در آستانه نابودی قطعی قرار دارد.\n"
        "تنها راه بازیابی، تمدید فوری اشتراک از طریق کارشناس پشتیبانی است:\n"
        f"💬 هماهنگی سریع: {SUPPORT_BALE_ID}\n"
        f"📞 تلفن: `{SUPPORT_PHONE}`"
    ),
    (
        "⛔ **اخطار فوری: مسدود شدن پایگاه داده و از دست رفتن تاریخچه**\n\n"
        "دسترسی به سیستم قطع شد. به علت عدم تمدید و نبود سرویس بکاپ، ریسک حذف همیشگی تمام سوابق بسیار بالاست.\n"
        "پیش از حذف کامل رکوردها از سرور، همین الان پیام دهید تا اکانت تمدید گردد:\n"
        f"💬 پشتیبانی رسمی: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "💣 **آخرین فرصت جلوگیری از پاک‌سازی دیتابیس!**\n\n"
        "حساب کاربری شما منقضی است و طبق دستورالعمل پاک‌سازی، به زودی تمامی فایل‌ها و دیتای متناظر زدوده می‌شوند.\n"
        "جهت تمدید آنی و جلوگیری از فاجعه حذف اطلاعات:\n"
        f"💬 پیام به پشتیبانی: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    )
]

EXPIRED_DAILY_TEMPLATES = [
    (
        "⚠️ **اخطار روزانه: فایل‌ها و سوابق شما در مراحل نهایی حذف قرار دارند**\n\n"
        "بیش از ۲۴ ساعت از انقضای حساب شما گذشته است. پردازش متوقف بوده و بازگردانی اطلاعات هر روز سخت‌تر و غیرممکن‌تر می‌شود.\n"
        "اگر اطلاعات برایتان اهمیت دارد، سریعاً لایسنس را تمدید فرمایید:\n"
        f"💬 پشتیبانی در بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🛑 **گزارش بحران: آزادسازی منابع و پاک‌سازی رکوردها**\n\n"
        "سیستم شما فاقد اعتبار است. دیتای ثبت‌شده در وضعیت ایزوله قرار دارد و به زودی به طور دائم پاک می‌شود.\n"
        "تماس اضطراری جهت بازیابی و تمدید:\n"
        f"💬 پشتیبانی در بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🔥 **هشدار انقضای مهلت استرداد داده‌ها**\n\n"
        "چند روز از اتمام زمان اشتراک سپری شده است. فرصت نجات اطلاعات شما رو به پایان است.\n"
        "جهت جلوگیری از حذف قطعی و ابدی فایل‌ها، پیام دهید:\n"
        f"💬 ارتباط با پشتیبانی: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    )
]

EXPIRED_WEEKLY_TEMPLATES = [
    (
        "⚠️ **اعلان هفتگی: اکانت شما در وضعیت بایگانی راکد و در آستانه امحا است**\n\n"
        "اشتراک سیستم شما منقضی شده و داده‌ها بدون پشتیبان رها شده‌اند. "
        "جهت بررسی امکان بازگردانی و شارژ مجدد حساب، با پشتیبانی تماس حاصل فرمایید:\n"
        f"💬 پشتیبانی بله: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    ),
    (
        "🛑 **یادآوری دوره‌ای: سیستم غیرفعال و ریسک از دست رفتن دائمی اطلاعات**\n\n"
        "حساب کاربری شما هنوز تمدید نشده است. جهت فعال‌سازی مجدد و ارتقا به نسخه پایدار با بکاپ دائمی:\n"
        f"💬 پیام به پشتیبانی: {SUPPORT_BALE_ID}\n"
        f"📞 تماس: `{SUPPORT_PHONE}`"
    )
]


def load_alert_state() -> Dict[str, Any]:
    """Loads alert tracking state from disk."""
    if not ALERT_STATE_FILE.exists():
        return {
            "last_alert_epoch": 0.0,
            "last_alert_stage": "",
            "counter_trial": 0,
            "counter_exp_immediate": 0,
            "counter_exp_daily": 0,
            "counter_exp_weekly": 0,
            "license_expires_at": 0.0
        }
    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_alert_epoch": 0.0,
            "last_alert_stage": "",
            "counter_trial": 0,
            "counter_exp_immediate": 0,
            "counter_exp_daily": 0,
            "counter_exp_weekly": 0,
            "license_expires_at": 0.0
        }


def save_alert_state(state: Dict[str, Any]) -> None:
    """Atomically writes alert tracking state to disk."""
    try:
        temp_file = ALERT_STATE_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        temp_file.replace(ALERT_STATE_FILE)
    except Exception as e:
        logger.error(f"Error saving alert state: {e}")


def get_all_target_chat_ids() -> List[str]:
    """
    Collects all unique user/chat IDs that should receive notifications:
    - Registered users who pressed /start in Bale (from registered_users.json)
    - User IDs configured in config.json
    - Super Admin ID
    """
    targets = set()

    # 1. Registered users from Bale listener
    try:
        from .bale_listener import load_registered_users
        reg_users = load_registered_users()
        for u in reg_users:
            uid = str(u.get("user_id", "")).strip()
            if uid:
                targets.add(uid)
    except Exception:
        pass

    # 2. Configured user IDs
    try:
        cfg = load_config()
        for uid in cfg.get("user_ids", []):
            s = str(uid).strip()
            if s:
                targets.add(s)
    except Exception:
        pass

    # 3. Super Admin
    targets.add(SUPER_ADMIN_ID_STR)

    return list(targets)


def broadcast_license_change(plan_title: str, duration_str: str, expires_at_str: str, is_trial: bool = False) -> None:
    """
    Broadcasts license activation / renewal event to all bot users in Bale.
    Runs asynchronously in a background thread.
    """
    cfg = load_config()
    token = cfg.get("bot_token", "").strip()
    if not token:
        logger.warning("No bot_token configured; skipping license broadcast.")
        return

    if is_trial:
        msg = (
            "🎉 **نسخه آزمایشی ۷۲ ساعته اکسیس پالس فعال شد!**\n\n"
            f"⏳ **مدت اعتبار:** {duration_str}\n"
            f"📅 **تاریخ و ساعت پایان:** `{expires_at_str}`\n\n"
            "⚠️ **هشدار مهم نگهداری اطلاعات:**\n"
            "به دلیل موقت بودن این حساب، سرور پشتیبان‌گیری خودکار (بکاپ) برای آن غیرفعال است. "
            "جهت جلوگیری از حذف اطلاعات و از دست رفتن فایل‌ها، پیش از اتمام مهلت اقدام به تمدید فرمایید.\n\n"
            f"💬 پشتیبانی و تمدید در بله: {SUPPORT_BALE_ID}\n"
            f"📞 تماس پشتیبانی: `{SUPPORT_PHONE}`"
        )
    else:
        msg = (
            "🎉 **اشتراک نرم‌افزار اکسیس پالس با موفقیت فعال / تمدید شد!**\n\n"
            f"💎 **پلن اشتراک:** {plan_title}\n"
            f"⏳ **مدت اعتبار:** {duration_str}\n"
            f"📅 **تاریخ پایان اعتبار:** `{expires_at_str}`\n\n"
            "✅ تمامی قابلیت‌های مانیتورینگ، پردازش و ارسال فایل‌ها فعال می‌باشند.\n\n"
            f"💬 ارتباط با پشتیبانی: {SUPPORT_BALE_ID}\n"
            f"📞 تماس: `{SUPPORT_PHONE}`"
        )

    targets = get_all_target_chat_ids()
    logger.info(f"Broadcasting license change to {len(targets)} targets: {plan_title}")
    broadcast_message_async(token, targets, msg)

    # Reset alert state for fresh schedule under new license
    state = load_alert_state()
    state["counter_trial"] = 0
    state["counter_exp_immediate"] = 0
    state["counter_exp_daily"] = 0
    state["counter_exp_weekly"] = 0
    state["last_alert_stage"] = "new_activation"
    # Delay first alert by 24h from activation
    state["last_alert_epoch"] = time.time()
    save_alert_state(state)


_check_lock = threading.Lock()

def check_and_send_license_alerts(force: bool = False) -> Optional[str]:
    """
    Periodic check to evaluate if a license expiration or data danger alert is due.
    Can be invoked from service_worker loop, GUI timer, or background monitor.
    """
    if not _check_lock.acquire(blocking=False):
        return None

    try:
        cfg = load_config()
        token = cfg.get("bot_token", "").strip()
        if not token:
            return None

        active, _, lic_info = is_license_active()
        now = time.time()
        state = load_alert_state()

        activated_at = float(lic_info.get("activated_at_epoch", 0.0) if "activated_at_epoch" in lic_info else 0.0)
        expires_at = float(lic_info.get("expires_at", 0.0))
        plan_id = str(lic_info.get("plan_id", ""))

        # If expires_at not in info (e.g. license inactive), attempt reading from file directly
        if expires_at <= 0:
            from .license_manager import get_license_file_data
            raw_lic = get_license_file_data()
            if raw_lic:
                expires_at = float(raw_lic.get("expires_at", 0.0))
                activated_at = float(raw_lic.get("activated_at", 0.0))
                plan_id = str(raw_lic.get("plan_id", ""))

        if expires_at <= 0:
            # No license ever activated
            return None

        last_alert = state.get("last_alert_epoch", 0.0)

        # Detect license extension/change
        if abs(expires_at - state.get("license_expires_at", 0.0)) > 60:
            state["license_expires_at"] = expires_at
            state["counter_trial"] = 0
            state["counter_exp_immediate"] = 0
            state["counter_exp_daily"] = 0
            state["counter_exp_weekly"] = 0
            save_alert_state(state)

        message_to_send = None
        current_stage = ""

        # --- Case A: License Active (Trial Mode) ---
        if active and now < expires_at:
            is_trial = "trial" in plan_id or expires_at - activated_at <= (75 * 3600)
            if is_trial:
                time_since_act = now - activated_at if activated_at > 0 else (72 * 3600 - (expires_at - now))
                # Start after 24 hours of trial activation
                if time_since_act >= (24 * 3600):
                    # Interval: Every 6 hours (21600 seconds)
                    if (now - last_alert >= 21600) or force:
                        idx = state.get("counter_trial", 0)
                        message_to_send = TRIAL_DANGER_TEMPLATES[idx % len(TRIAL_DANGER_TEMPLATES)]
                        state["counter_trial"] = idx + 1
                        current_stage = f"trial_active_6h_{idx}"

        # --- Case B: License Expired ---
        elif now >= expires_at:
            time_since_exp = now - expires_at

            # Phase 1: First 24 hours after expiration -> Every 6 hours (21600 s)
            if time_since_exp <= (24 * 3600):
                if (now - last_alert >= 21600) or force:
                    idx = state.get("counter_exp_immediate", 0)
                    message_to_send = EXPIRED_IMMEDIATE_TEMPLATES[idx % len(EXPIRED_IMMEDIATE_TEMPLATES)]
                    state["counter_exp_immediate"] = idx + 1
                    current_stage = f"expired_immediate_6h_{idx}"

            # Phase 2: Day 2 to Day 7 after expiration -> Every 24 hours (86400 s)
            elif (24 * 3600) < time_since_exp <= (7 * 86400):
                if (now - last_alert >= 86400) or force:
                    idx = state.get("counter_exp_daily", 0)
                    message_to_send = EXPIRED_DAILY_TEMPLATES[idx % len(EXPIRED_DAILY_TEMPLATES)]
                    state["counter_exp_daily"] = idx + 1
                    current_stage = f"expired_daily_24h_{idx}"

            # Phase 3: Beyond 1 week after expiration -> Weekly (7 * 86400 s)
            else:
                if (now - last_alert >= 7 * 86400) or force:
                    idx = state.get("counter_exp_weekly", 0)
                    message_to_send = EXPIRED_WEEKLY_TEMPLATES[idx % len(EXPIRED_WEEKLY_TEMPLATES)]
                    state["counter_exp_weekly"] = idx + 1
                    current_stage = f"expired_weekly_{idx}"

        if message_to_send:
            targets = get_all_target_chat_ids()
            logger.info(f"Sending license risk alert ({current_stage}) to {len(targets)} targets.")
            broadcast_message_async(token, targets, message_to_send)

            state["last_alert_epoch"] = now
            state["last_alert_stage"] = current_stage
            save_alert_state(state)
            return current_stage

        return None
    finally:
        _check_lock.release()
