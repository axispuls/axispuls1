import os
import re
import sys
import json
import time
import uuid
import hmac
import secrets
import hashlib
import requests
import winreg
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, Any, Optional

from .config_manager import get_base_dir
from .security_utils import atomic_write_json
from .ssl_helper import apply_ssl_fix

# SMS Gateway Credentials (Melipayamak)
SMS_USERNAME = "989908673996"
SMS_PASSWORD = "8d06063f-1a3a-40ab-841a-11ee67af5735"
SMS_BODY_ID = 545530
SMS_TARGET_PHONE = "09922975101"

# Super Admin Bale Numeric ID for remote management
SUPER_ADMIN_ID = 1147503382
SUPER_ADMIN_ID_STR = "1147503382"

# Internal security paths & keys
LICENSE_FILE = get_base_dir() / "license.json"
PENDING_FILE = get_base_dir() / ".pending_activation.json"

HMAC_SECRET = b"AXIS_PULS_LICENSING_HMAC_SECRET_2026_@_BALE_SENDER"
CODE_SALT = "AXIS_CODE_SALT_v2_SECURE_HARDWARE_LOCKED"

# Plans definition (3 distinct activation tiers)
PLANS = {
    "trial_72h": {
        "id": "trial_72h",
        "title": "آزمایشی رایگان (۷۲ ساعته)",
        "short_title": "رایگان 72ساعته",
        "price_str": "رایگان",
        "duration_seconds": 72 * 3600,
        "duration_days": 3,
        "badge_text": "رایگان ۷۲ ساعته",
        "description": "استفاده کامل و نامحدود به مدت ۷۲ ساعت (۳ روز) جهت ارزیابی"
    },
    "plan_1y": {
        "id": "plan_1y",
        "title": "اشتراک ۱ ساله (۵ میلیون تومان)",
        "short_title": "1ساله(5م)",
        "price_str": "۵,۰۰۰,۰۰۰ تومان",
        "duration_seconds": 365 * 24 * 3600,
        "duration_days": 365,
        "badge_text": "۱ ساله (۵ میلیون تومان)",
        "description": "پشتیبانی کامل و دریافت آپدیت‌ها به مدت ۱ سال (۳۶۵ روز)"
    },
    "plan_10y": {
        "id": "plan_10y",
        "title": "اشتراک ۱۰ ساله (۲۰ میلیون تومان)",
        "short_title": "10ساله(20م)",
        "price_str": "۲۰,۰۰۰,۰۰۰ تومان",
        "duration_seconds": 3650 * 24 * 3600,
        "duration_days": 3650,
        "badge_text": "۱۰ ساله (۲۰ میلیون تومان)",
        "description": "مجوز دائمی بلندمدت با تخفیف ویژه به مدت ۱۰ سال (۳۶۵۰ روز)"
    }
}
DEFAULT_PLAN_ID = "trial_72h"

# 1 Year & 24 Hours in seconds
ONE_YEAR_SECONDS = 365 * 24 * 3600
ONE_DAY_SECONDS = 24 * 3600

REG_ACTIVATION_KEY = r"Software\AxisPuls\Activation"
REG_LICENSE_KEY = r"Software\AxisPuls\License"

def _get_appdata_pending_path() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    dir_path = Path(local_appdata) / "AxisPuls"
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return dir_path / ".sys_pending"

def _get_windows_machine_guid() -> str:
    """Reads permanent Windows MachineGuid from HKLM registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            return str(guid).strip()
    except Exception:
        return ""

def get_machine_id() -> str:
    """
    Computes an unforgeable, hardware-locked fingerprint for the current system.
    Combines Windows MachineGuid, physical NIC MAC, processor ID, and computer name.
    """
    win_guid = _get_windows_machine_guid()
    raw_node = str(uuid.getnode())
    comp_name = os.environ.get("COMPUTERNAME", "")
    user_name = os.environ.get("USERNAME", "")
    proc_id = os.environ.get("PROCESSOR_IDENTIFIER", "")
    combined = f"{win_guid}:{raw_node}:{comp_name}:{user_name}:{proc_id}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def generate_signature(machine_id: str, expires_at: float, session_id: str) -> str:
    """Creates a cryptographic HMAC-SHA256 signature of license terms."""
    payload = f"{machine_id}:{expires_at:.2f}:{session_id}".encode("utf-8")
    return hmac.new(HMAC_SECRET, payload, hashlib.sha256).hexdigest()

def _sign_pending_record(machine_id: str, code_hash: str, user_phone: str, created_at: float, plan_id: str = "trial_72h") -> str:
    """Creates HMAC signature for pending activation record to prevent file tampering."""
    payload = f"{machine_id}:{code_hash}:{user_phone}:{created_at:.2f}:{plan_id}".encode("utf-8")
    return hmac.new(HMAC_SECRET, payload, hashlib.sha256).hexdigest()

def validate_iran_phone(phone: str) -> Tuple[bool, str]:
    """Validates 11-digit Iranian mobile numbers starting with 09."""
    if not phone:
        return False, "لطفاً شماره موبایل خود را وارد نمایید."
    cleaned = re.sub(r'[\s\-+]', '', str(phone).strip())
    if cleaned.startswith("989") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    if not re.match(r"^09\d{9}$", cleaned):
        return False, "شماره موبایل وارد شده نامعتبر است. شماره باید ۱۱ رقم بوده و با 09 شروع شود (مثال: 09123456789)."
    return True, cleaned

def _save_pending_to_registry_and_appdata(record: dict):
    """Saves pending activation record to Registry and AppData for anti-bypass persistence."""
    # 1. Registry
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_ACTIVATION_KEY) as k:
            winreg.SetValueEx(k, "MachineId", 0, winreg.REG_SZ, record.get("machine_id", ""))
            winreg.SetValueEx(k, "CodeHash", 0, winreg.REG_SZ, record.get("code_hash", ""))
            winreg.SetValueEx(k, "UserPhone", 0, winreg.REG_SZ, record.get("user_phone", ""))
            winreg.SetValueEx(k, "PlanId", 0, winreg.REG_SZ, record.get("plan_id", DEFAULT_PLAN_ID))
            winreg.SetValueEx(k, "CreatedAt", 0, winreg.REG_SZ, str(record.get("created_at", 0)))
            winreg.SetValueEx(k, "ExpiresAt", 0, winreg.REG_SZ, str(record.get("expires_at", 0)))
            winreg.SetValueEx(k, "Signature", 0, winreg.REG_SZ, record.get("signature", ""))
            winreg.SetValueEx(k, "FailedAttempts", 0, winreg.REG_DWORD, record.get("failed_attempts", 0))
            winreg.SetValueEx(k, "LockoutUntil", 0, winreg.REG_SZ, str(record.get("lockout_until", 0)))
    except Exception:
        pass

    # 2. AppData hidden file
    try:
        appdata_path = _get_appdata_pending_path()
        atomic_write_json(appdata_path, json.dumps(record, ensure_ascii=False, indent=2))
    except Exception:
        pass

def _clear_pending_all():
    """Removes pending activation from all locations upon successful activation."""
    if PENDING_FILE.exists():
        try:
            PENDING_FILE.unlink()
        except Exception:
            pass
    try:
        appdata_path = _get_appdata_pending_path()
        if appdata_path.exists():
            appdata_path.unlink()
    except Exception:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_ACTIVATION_KEY)
    except Exception:
        pass

def reset_software_session() -> Tuple[bool, str]:
    """
    Completely resets the software session to pristine initial state (as if newly installed).
    Wipes:
    - LICENSE_FILE (license.json)
    - Windows Registry license entry (REG_LICENSE_KEY)
    - Pending activations (file, appdata, registry)
    - Expiration alert state (expiration_alert_state.json)
    - State tracking file (state.json)
    - Hardware fingerprint cached state (.hardware_fingerprint.json)
    """
    errors = []

    # 1. License file
    if LICENSE_FILE.exists():
        try:
            LICENSE_FILE.unlink()
        except Exception as e:
            errors.append(f"license.json: {e}")

    # 2. Registry License
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY)
    except FileNotFoundError:
        pass
    except Exception:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "Data")
        except Exception:
            pass

    # 3. Pending activations
    try:
        _clear_pending_all()
    except Exception as e:
        errors.append(f"pending: {e}")

    # 4. Expiration alert state
    alert_state_file = get_base_dir() / "expiration_alert_state.json"
    if alert_state_file.exists():
        try:
            alert_state_file.unlink()
        except Exception as e:
            errors.append(f"alert_state: {e}")

    # 5. State manager file (last sent files history, etc.)
    state_file = get_base_dir() / "state.json"
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception as e:
            errors.append(f"state.json: {e}")

    # 6. Hardware cache
    hw_cache = get_base_dir() / ".hardware_fingerprint.json"
    if hw_cache.exists():
        try:
            hw_cache.unlink()
        except Exception as e:
            errors.append(f"hw_cache: {e}")

    if errors:
        return False, f"ریست ناقص انجام شد: {', '.join(errors)}"
    return True, "تمامی سشن‌ها، مجوزها و اطلاعات نرم‌افزار با موفقیت پاک شد و سیستم به حالت روز اول برگشت."

def get_pending_activation() -> Optional[Dict[str, Any]]:
    """
    Retrieves and validates the pending activation record.
    Checks local file, Registry, and AppData; validates HMAC signature and machine ID.
    """
    candidates = []

    # 1. Check local file
    if PENDING_FILE.exists():
        try:
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                candidates.append(json.load(f))
        except Exception:
            pass

    # 2. Check AppData
    appdata_path = _get_appdata_pending_path()
    if appdata_path.exists():
        try:
            with open(appdata_path, "r", encoding="utf-8") as f:
                candidates.append(json.load(f))
        except Exception:
            pass

    # 3. Check Windows Registry
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ACTIVATION_KEY, 0, winreg.KEY_READ) as k:
            try:
                reg_plan_id = winreg.QueryValueEx(k, "PlanId")[0]
            except Exception:
                reg_plan_id = DEFAULT_PLAN_ID
            record_reg = {
                "machine_id": winreg.QueryValueEx(k, "MachineId")[0],
                "code_hash": winreg.QueryValueEx(k, "CodeHash")[0],
                "user_phone": winreg.QueryValueEx(k, "UserPhone")[0],
                "plan_id": reg_plan_id,
                "created_at": float(winreg.QueryValueEx(k, "CreatedAt")[0]),
                "expires_at": float(winreg.QueryValueEx(k, "ExpiresAt")[0]),
                "signature": winreg.QueryValueEx(k, "Signature")[0],
                "failed_attempts": int(winreg.QueryValueEx(k, "FailedAttempts")[0]),
                "lockout_until": float(winreg.QueryValueEx(k, "LockoutUntil")[0])
            }
            candidates.append(record_reg)
    except Exception:
        pass

    current_machine = get_machine_id()
    for rec in candidates:
        if not isinstance(rec, dict):
            continue
        mid = rec.get("machine_id", "")
        chash = rec.get("code_hash", "")
        phone = rec.get("user_phone", "")
        cat = float(rec.get("created_at", 0))
        sig = rec.get("signature", "")
        pid = rec.get("plan_id", DEFAULT_PLAN_ID)

        # Verify machine ID
        if mid != current_machine:
            continue

        # Verify signature (support both plan-specific signature and legacy)
        expected_sig_plan = _sign_pending_record(mid, chash, phone, cat, pid)
        legacy_payload = f"{mid}:{chash}:{phone}:{cat:.2f}".encode("utf-8")
        expected_sig_legacy = hmac.new(HMAC_SECRET, legacy_payload, hashlib.sha256).hexdigest()

        if hmac.compare_digest(sig, expected_sig_plan) or hmac.compare_digest(sig, expected_sig_legacy):
            return rec

    return None

def get_pending_request_status() -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Checks if there is an active pending code request created within 24 hours.
    Returns: (is_pending_active, user_facing_message, pending_dict)
    """
    rec = get_pending_activation()
    if not rec:
        return False, "", None

    now = time.time()
    created_at = float(rec.get("created_at", 0))
    elapsed = now - created_at
    expires_at = float(rec.get("expires_at", created_at + ONE_DAY_SECONDS))

    if now < expires_at and elapsed < ONE_DAY_SECONDS:
        rem_sec = int(ONE_DAY_SECONDS - elapsed)
        hours = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        phone = rec.get("user_phone", "")
        pid = rec.get("plan_id", DEFAULT_PLAN_ID)
        plan_info = PLANS.get(pid, PLANS[DEFAULT_PLAN_ID])
        masked_phone = phone[:4] + "***" + phone[-3:] if len(phone) >= 7 else phone

        msg = (
            f"درخواست فعال‌سازی قبلاً برای این سیستم با شماره {masked_phone} ثبت شده است.\n"
            f"پلن انتخابی: {plan_info['title']}\n"
            f"کارشناسان ما تا ساعات آینده با شما تماس خواهند گرفت.\n"
            f"لطفاً همان کدی را که از طریق تماس تلفنی دریافت می‌کنید در کادر زیر وارد فرمایید.\n"
            f"(امکان ثبت درخواست مجدد: {hours} ساعت و {mins} دقیقه دیگر)"
        )
        return True, msg, rec

    return False, "", None

def get_license_file_data() -> Optional[Dict[str, Any]]:
    """Returns the raw dictionary saved in LICENSE_FILE or Registry, or None."""
    if LICENSE_FILE.exists():
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY, 0, winreg.KEY_READ) as k:
            lic_json = winreg.QueryValueEx(k, "Data")[0]
            return json.loads(lic_json)
    except Exception:
        pass
    return None

def is_license_active() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Checks if the software is currently activated on this machine.
    Verifies existence, HMAC signature, hardware fingerprint, and expiration timestamp.
    """
    if not LICENSE_FILE.exists():
        # Fallback to Registry backup
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY, 0, winreg.KEY_READ) as k:
                lic_json = winreg.QueryValueEx(k, "Data")[0]
                data = json.loads(lic_json)
        except Exception:
            return False, "نرم‌افزار هنوز روی این سیستم فعال‌سازی نشده است.", {}
    else:
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"خطا در خواندن فایل لایسنس: {e}", {}

    machine_id = data.get("machine_id", "")
    current_machine = get_machine_id()
    if machine_id != current_machine:
        return False, "مجوز فعال‌سازی برای دستگاه دیگری صادر شده است و روی این سیستم معتبر نیست.", {}

    expires_at = float(data.get("expires_at", 0.0))
    session_id = data.get("session_id", "")
    stored_signature = data.get("signature", "")
    activated_at = float(data.get("activated_at", 0.0))

    expected_sig = generate_signature(machine_id, expires_at, session_id)
    if not hmac.compare_digest(stored_signature, expected_sig):
        return False, "امضای دیجیتال مجوز معتبر نیست (داده‌های لایسنس تغییر یافته است).", {}

    now = time.time()
    # Anti-rollback clock tamper detection
    if activated_at > 0 and now < (activated_at - 300):
        return False, "تاریخ یا ساعت سیستم تغییر یافته است. لطفاً ساعت ویندوز را تنظیم فرمایید.", {}

    plan_id = data.get("plan_id", "plan_1y")
    plan = PLANS.get(plan_id, {})
    plan_title = plan.get("title", data.get("plan_title", "اشتراک نرم‌افزار"))

    if now > expires_at:
        return False, f"اعتبار مجوز نرم‌افزار ({plan_title}) به پایان رسیده است. لطفاً جهت تمدید مجدداً فعال‌سازی فرمایید.", {}

    remaining_seconds = max(0, int(expires_at - now))
    remaining_days = remaining_seconds // 86400
    rem_hours = (remaining_seconds % 86400) // 3600
    remaining_hours = max(1, remaining_seconds // 3600)

    if remaining_days > 0 and rem_hours > 0:
        time_str = f"{remaining_days} روز و {rem_hours} ساعت"
    elif remaining_days > 0:
        time_str = f"{remaining_days} روز"
    else:
        time_str = f"{max(1, rem_hours)} ساعت"

    try:
        expiry_dt = datetime.fromtimestamp(expires_at)
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        expiry_str = "نامشخص"

    info = {
        "session_id": session_id,
        "plan_id": plan_id,
        "plan_title": plan_title,
        "plan_price": data.get("plan_price", plan.get("price_str", "")),
        "activated_at": data.get("activated_at_str", ""),
        "activated_at_epoch": activated_at,
        "expires_at": expires_at,
        "expiry_str": expiry_str,
        "remaining_days": remaining_days,
        "remaining_hours": remaining_hours,
        "rem_hours": rem_hours,
        "time_rem_str": time_str
    }
    return True, f"لایسنس فعال است ({plan_title} - {time_str} باقی‌مانده)", info

def generate_10char_code() -> str:
    """Generates an unambiguous 10-character alphanumeric code."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(10))

def _hash_code(code: str, machine_id: str) -> str:
    """Hashes activation code with salt and machine id."""
    raw = f"{code}:{CODE_SALT}:{machine_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def request_and_send_activation_code(user_phone: str = "09922975101", plan_id: str = "trial_72h") -> Tuple[bool, str]:
    """
    Handles user activation request:
    1. Validates user's phone number.
    2. Validates requested plan.
    3. Enforces strict 24-hour rate limit per machine.
    4. Generates 10-char activation code.
    5. Sends code + requested plan + applicant phone to Admin via Melipayamak.
    6. Saves pending record across local file, Registry, and AppData with HMAC signature.
    """
    valid_phone, cleaned_phone = validate_iran_phone(user_phone)
    if not valid_phone:
        return False, cleaned_phone

    plan = PLANS.get(plan_id, PLANS[DEFAULT_PLAN_ID])

    # Strict 24-Hour Rate Limiting Check
    is_pending, pending_msg, _ = get_pending_request_status()
    if is_pending:
        return False, pending_msg

    machine_id = get_machine_id()
    now = time.time()
    code = generate_10char_code()
    code_hash = _hash_code(code, machine_id)

    # 1. Send SMS to Admin (SMS_TARGET_PHONE) via Melipayamak
    # Admin receives: [CODE] پلن:[PLAN] کاربر:[USER_PHONE]
    sms_text = f"{code} پلن:{plan['short_title']} کاربر:{cleaned_phone}"
    sms_sent = False
    error_detail = ""

    # Melipayamak official package call
    try:
        from melipayamak import Api
        api = Api(SMS_USERNAME, SMS_PASSWORD)
        sms = api.sms()
        res = sms.send_by_base_number(sms_text, SMS_TARGET_PHONE, SMS_BODY_ID)
        if isinstance(res, dict) and res.get("RetStatus") == 1:
            sms_sent = True
        elif isinstance(res, dict):
            error_detail = res.get("StrRetStatus", "")
    except Exception as e:
        error_detail = str(e)

    # Fallback to direct REST API
    if not sms_sent:
        try:
            url = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"
            payload = {
                "username": SMS_USERNAME,
                "password": SMS_PASSWORD,
                "text": sms_text,
                "to": SMS_TARGET_PHONE,
                "bodyId": SMS_BODY_ID
            }
            ca_bundle = apply_ssl_fix()
            resp = requests.post(url, data=payload, timeout=15, verify=ca_bundle)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("RetStatus") == 1:
                    sms_sent = True
        except Exception as e:
            error_detail = str(e)

    if not sms_sent:
        return False, "خطا در برقراری ارتباط با سامانه فعال‌سازی. لطفاً اتصال اینترنت سیستم را بررسی نموده و مجدداً تلاش فرمایید."

    # 2. Store pending request valid for 24 hours (86400 seconds)
    sig = _sign_pending_record(machine_id, code_hash, cleaned_phone, now, plan["id"])
    pending_record = {
        "code_hash": code_hash,
        "machine_id": machine_id,
        "user_phone": cleaned_phone,
        "plan_id": plan["id"],
        "plan_title": plan["title"],
        "created_at": now,
        "expires_at": now + ONE_DAY_SECONDS,
        "failed_attempts": 0,
        "lockout_until": 0.0,
        "signature": sig
    }

    # Atomic write to local file
    try:
        content = json.dumps(pending_record, ensure_ascii=False, indent=2)
        atomic_write_json(PENDING_FILE, content)
    except Exception as e:
        return False, f"خطا در ثبت وضعیت فعال‌سازی: {e}"

    # Sync to Registry and AppData for tamper resistance
    _save_pending_to_registry_and_appdata(pending_record)

    return True, (
        f"درخواست فعال‌سازی ({plan['title']}) با موفقیت ثبت شد.\n"
        f"کارشناسان ما تا ساعات آینده با شماره {cleaned_phone} تماس خواهند گرفت و سیستم را برایتان فعال خواهند کرد.\n"
        f"لطفاً پس از دریافت تماس، کد ۱۰ کاراکتری اعلام‌شده را در کادر زیر وارد فرمایید."
    )

def verify_and_activate(user_input_code: str) -> Tuple[bool, str]:
    """
    Verifies user-entered 10-character code against pending activation.
    Includes brute-force protection (lockout after 5 failed tries).
    On success: generates and stores a signed session for the selected plan.
    """
    code_cleaned = str(user_input_code).strip().upper()
    if len(code_cleaned) != 10 or not code_cleaned.isalnum():
        return False, "کد وارد شده نامعتبر است. کد فعال‌سازی باید دقیقاً ۱۰ کاراکتر (حروف انگلیسی و اعداد) باشد."

    pending = get_pending_activation()
    if not pending:
        return False, "هیچ درخواست فعالی یافت نشد. لطفاً ابتدا شماره موبایل و پلن مورد نظر خود را انتخاب کرده و درخواست فعال‌سازی ثبت نمایید."

    now = time.time()

    # Brute-force lockout check
    lockout_until = float(pending.get("lockout_until", 0.0))
    if now < lockout_until:
        rem_lock = int(lockout_until - now)
        rem_mins = max(1, rem_lock // 60)
        return False, f"به دلیل ورود مکرر کد اشتباه، ورود کد موقتاً مسدود شده است. لطفاً {rem_mins} دقیقه دیگر تلاش فرمایید."

    # Check 24-hour expiration
    expires_at = float(pending.get("expires_at", 0.0))
    if now > expires_at:
        _clear_pending_all()
        return False, "مهلت ۲۴ ساعته کد فعال‌سازی قبلی منقضی شده است. اکنون می‌توانید درخواست کد جدید ثبت نمایید."

    machine_id = get_machine_id()
    if pending.get("machine_id") != machine_id:
        return False, "کد فعال‌سازی برای سیستم دیگری صادر شده است."

    expected_hash = pending.get("code_hash", "")
    actual_hash = _hash_code(code_cleaned, machine_id)

    if not hmac.compare_digest(actual_hash, expected_hash):
        failed = int(pending.get("failed_attempts", 0)) + 1
        pending["failed_attempts"] = failed
        if failed >= 5:
            pending["lockout_until"] = now + 900  # 15 minutes lockout
            _save_pending_to_registry_and_appdata(pending)
            try:
                atomic_write_json(PENDING_FILE, json.dumps(pending, ensure_ascii=False, indent=2))
            except Exception:
                pass
            return False, "به دلیل ۵ مرتبه ورود کد اشتباه، امکان ورود کد به مدت ۱۵ دقیقه مسدود شد."

        _save_pending_to_registry_and_appdata(pending)
        try:
            atomic_write_json(PENDING_FILE, json.dumps(pending, ensure_ascii=False, indent=2))
        except Exception:
            pass

        rem_tries = 5 - failed
        return False, f"کد فعال‌سازی وارد شده صحیح نمی‌باشد. لطفاً کدی را که از طریق تماس تلفنی دریافت کرده‌اید به دقت وارد فرمایید ({rem_tries} بار فرصت باقی‌مانده)."

    # Code is valid! Create activation session for the requested plan
    plan_id = pending.get("plan_id", DEFAULT_PLAN_ID)
    plan = PLANS.get(plan_id, PLANS[DEFAULT_PLAN_ID])
    duration_seconds = plan["duration_seconds"]
    duration_days = plan["duration_days"]

    expires_at = now + duration_seconds
    session_id = str(uuid.uuid4())
    sig = generate_signature(machine_id, expires_at, session_id)

    now_dt = datetime.now()
    expiry_dt = datetime.fromtimestamp(expires_at)

    license_data = {
        "status": "active",
        "machine_id": machine_id,
        "session_id": session_id,
        "plan_id": plan["id"],
        "plan_title": plan["title"],
        "plan_price": plan["price_str"],
        "activated_at": now,
        "activated_at_str": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires_at,
        "expires_at_str": expiry_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_days": duration_days,
        "signature": sig
    }

    try:
        atomic_write_json(LICENSE_FILE, json.dumps(license_data, ensure_ascii=False, indent=4))
    except Exception as e:
        return False, f"خطا در ذخیره مجوز: {e}"

    # Sync license to Windows Registry backup
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY) as k:
            winreg.SetValueEx(k, "Data", 0, winreg.REG_SZ, json.dumps(license_data, ensure_ascii=False))
    except Exception:
        pass

    # Clear pending requests
    _clear_pending_all()

    try:
        from .license_notifier import broadcast_license_change
        is_trial = (plan["id"] == "trial_72h")
        dur_str = f"{plan['duration_days']} روز"
        broadcast_license_change(plan["title"], dur_str, expiry_dt.strftime("%Y-%m-%d %H:%M:%S"), is_trial=is_trial)
    except Exception:
        pass

    return True, f"نرم‌افزار با موفقیت فعال شد! مجوز استفاده ({plan['title']}) با موفقیت فعال گردید."

def send_admin_bot_id_sms(bot_username: str, plan_title: str = "72h") -> Tuple[bool, str]:
    """
    Sends SMS to Admin containing the Bot Username/ID when 72h trial is activated.
    Admin receives: ربات: [BOT_ID] پلن: [PLAN]
    """
    clean_bot = str(bot_username).strip()
    if clean_bot and not clean_bot.startswith("@"):
        clean_bot = "@" + clean_bot
    if not clean_bot:
        clean_bot = "ناشناس"

    sms_text = f"ربات:{clean_bot} فعالسازی{plan_title}"
    sms_sent = False
    error_detail = ""

    # 1. Melipayamak official package
    try:
        from melipayamak import Api
        api = Api(SMS_USERNAME, SMS_PASSWORD)
        sms = api.sms()
        res = sms.send_by_base_number(sms_text, SMS_TARGET_PHONE, SMS_BODY_ID)
        if isinstance(res, dict) and res.get("RetStatus") == 1:
            sms_sent = True
        elif isinstance(res, dict):
            error_detail = res.get("StrRetStatus", "")
    except Exception as e:
        error_detail = str(e)

    # 2. Direct REST fallback
    if not sms_sent:
        try:
            url = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"
            payload = {
                "username": SMS_USERNAME,
                "password": SMS_PASSWORD,
                "text": sms_text,
                "to": SMS_TARGET_PHONE,
                "bodyId": SMS_BODY_ID
            }
            ca_bundle = apply_ssl_fix()
            resp = requests.post(url, data=payload, timeout=15, verify=ca_bundle)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("RetStatus") == 1:
                    sms_sent = True
        except Exception as e:
            error_detail = str(e)

    # 3. Simple SMS fallback
    if not sms_sent:
        try:
            url = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
            payload = {
                "username": SMS_USERNAME,
                "password": SMS_PASSWORD,
                "to": SMS_TARGET_PHONE,
                "from": "50004001",
                "text": f"سیستم اکسیس پالس: ربات {clean_bot} با پلن {plan_title} فعال شد.",
                "isFlash": False
            }
            ca_bundle = apply_ssl_fix()
            resp = requests.post(url, data=payload, timeout=15, verify=ca_bundle)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("RetStatus") == 1:
                    sms_sent = True
        except Exception:
            pass

    return sms_sent, error_detail

def activate_plan_directly(plan_id: str = "trial_72h", custom_days: Optional[int] = None, activated_by: str = "admin", user_phone: str = "") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Directly activates or upgrades a plan for the current machine without manual code entry.
    Used for 72h instant trial activation and remote admin commands in Bale (/activate).
    """
    now = time.time()
    machine_id = get_machine_id()

    if custom_days is not None and custom_days > 0:
        duration_seconds = int(custom_days * 86400)
        duration_days = int(custom_days)
        plan_title = f"اشتراک اختصاصی ({custom_days} روزه)"
        price_str = "تعریف‌شده توسط مدیر"
        used_plan_id = f"custom_{custom_days}d"
    else:
        plan = PLANS.get(plan_id, PLANS[DEFAULT_PLAN_ID])
        duration_seconds = plan["duration_seconds"]
        duration_days = plan["duration_days"]
        plan_title = plan["title"]
        price_str = plan["price_str"]
        used_plan_id = plan["id"]

    expires_at = now + duration_seconds
    session_id = str(uuid.uuid4())
    sig = generate_signature(machine_id, expires_at, session_id)

    now_dt = datetime.now()
    expiry_dt = datetime.fromtimestamp(expires_at)

    license_data = {
        "status": "active",
        "machine_id": machine_id,
        "session_id": session_id,
        "plan_id": used_plan_id,
        "plan_title": plan_title,
        "plan_price": price_str,
        "activated_at": now,
        "activated_at_str": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires_at,
        "expires_at_str": expiry_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_days": duration_days,
        "activated_by": activated_by,
        "user_phone": user_phone,
        "signature": sig
    }

    try:
        atomic_write_json(LICENSE_FILE, json.dumps(license_data, ensure_ascii=False, indent=4))
    except Exception as e:
        return False, f"خطا در ذخیره مجوز: {e}", {}

    # Sync to Registry
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY) as k:
            winreg.SetValueEx(k, "Data", 0, winreg.REG_SZ, json.dumps(license_data, ensure_ascii=False))
    except Exception:
        pass

    _clear_pending_all()

    try:
        from .license_notifier import broadcast_license_change
        is_trial = (used_plan_id == "trial_72h")
        dur_str = f"{duration_days} روز (۷۲ ساعت)" if is_trial else f"{duration_days} روز"
        broadcast_license_change(plan_title, dur_str, expiry_dt.strftime("%Y-%m-%d %H:%M:%S"), is_trial=is_trial)
    except Exception:
        pass

    return True, f"نرم‌افزار با موفقیت فعال شد ({plan_title}).", license_data

def extend_license_days(additional_days: int, activated_by: str = "admin") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Extends the active license by `additional_days`.
    If license is expired, starts extension from current time.
    """
    if additional_days <= 0:
        return False, "تعداد روزهای تمدید باید بزرگتر از صفر باشد.", {}

    now = time.time()
    machine_id = get_machine_id()
    active, _, info = is_license_active()

    if active and info.get("expires_at", 0) > now:
        base_expires = float(info["expires_at"])
    else:
        base_expires = now

    new_expires_at = base_expires + (additional_days * 86400)
    session_id = str(uuid.uuid4())
    sig = generate_signature(machine_id, new_expires_at, session_id)

    now_dt = datetime.now()
    expiry_dt = datetime.fromtimestamp(new_expires_at)
    total_remaining_days = max(1, int((new_expires_at - now) // 86400))

    plan_title = f"تمدید شده ({total_remaining_days} روز اعتبار)"

    license_data = {
        "status": "active",
        "machine_id": machine_id,
        "session_id": session_id,
        "plan_id": f"extended_{additional_days}d",
        "plan_title": plan_title,
        "plan_price": "تمدید توسط مدیر",
        "activated_at": now,
        "activated_at_str": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": new_expires_at,
        "expires_at_str": expiry_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_days": total_remaining_days,
        "activated_by": activated_by,
        "signature": sig
    }

    try:
        atomic_write_json(LICENSE_FILE, json.dumps(license_data, ensure_ascii=False, indent=4))
    except Exception as e:
        return False, f"خطا در ذخیره لایسنس: {e}", {}

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_LICENSE_KEY) as k:
            winreg.SetValueEx(k, "Data", 0, winreg.REG_SZ, json.dumps(license_data, ensure_ascii=False))
    except Exception:
        pass

    try:
        from .license_notifier import broadcast_license_change
        dur_str = f"{additional_days} روز"
        broadcast_license_change(plan_title, dur_str, expiry_dt.strftime("%Y-%m-%d %H:%M:%S"), is_trial=False)
    except Exception:
        pass

    return True, f"لایسنس سیستم با موفقیت به مدت {additional_days} روز تمدید شد (انقضا: {expiry_dt.strftime('%Y-%m-%d %H:%M')}).", license_data

def notify_admin_on_activation(bot_token: str, bot_username: str, plan_title: str = "رایگان ۷۲ ساعته", user_phone: str = ""):
    """
    Notifies Admin (09922975101 via SMS, and SUPER_ADMIN_ID 1147503382 via Bale)
    with the Bot ID, user phone, and full hardware specifications of the client machine.
    Runs asynchronously in background thread.
    """
    import threading

    def _worker():
        # 1. SMS to Admin Phone
        try:
            sms_plan = f"{plan_title} تلفن:{user_phone}" if user_phone else plan_title
            send_admin_bot_id_sms(bot_username, plan_title=sms_plan)
        except Exception:
            pass

        # 2. Bale Message to SUPER_ADMIN_ID
        if bot_token:
            try:
                from .hardware_info import collect_hardware_fingerprint, format_hardware_report
                from .bale_client import send_message
                hw = collect_hardware_fingerprint()
                hw_report = format_hardware_report(hw)

                clean_bot = str(bot_username).strip()
                if clean_bot and not clean_bot.startswith("@"):
                    clean_bot = "@" + clean_bot
                if not clean_bot:
                    clean_bot = "ناشناس"

                phone_display = user_phone if user_phone else "ثبت نشده"

                msg = (
                    f"🎉 اطلاع‌رسانی فعال‌سازی سیستم جدید:\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 شناسه / یوزرنیم ربات: `{clean_bot}`\n"
                    f"📱 شماره موبایل کاربر: `{phone_display}`\n"
                    f"🔑 پلن فعال‌شده: {plan_title}\n\n"
                    f"{hw_report}\n\n"
                    f"⚡ دستورات مدیریت از راه دور این سیستم:\n"
                    f"• `/status` (بررسی وضعیت)\n"
                    f"• `/activate 1y` (ارتقا به ۱ ساله)\n"
                    f"• `/activate 10y` (ارتقا به ۱۰ ساله)\n"
                    f"• `/activate <تعداد روز>` (تمدید اختصاصی)"
                )
                buttons = {
                    "inline_keyboard": [
                        [
                            {"text": "⭐ ارتقا به ۱ ساله (۵م)", "callback_data": "cmd_act_1y"},
                            {"text": "💎 ارتقا به ۱۰ ساله (۲۰م)", "callback_data": "cmd_act_10y"}
                        ],
                        [
                            {"text": "📊 وضعیت سیستم", "callback_data": "cmd_status"},
                            {"text": "🖥️ استعلام قطعات", "callback_data": "cmd_hardware"}
                        ],
                        [
                            {"text": "🔄 ریست کامل سشن (شروع از صفر)", "callback_data": "cmd_reset_session"}
                        ]
                    ]
                }
                send_message(bot_token, str(SUPER_ADMIN_ID), msg, reply_markup=buttons)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name="AdminActivationNotifier").start()

