import os
import sys

# Ensure valid SSL CA bundle for requests across PyInstaller parent/child lifecycles
try:
    import certifi
    valid_ca = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = valid_ca
    os.environ['CURL_CA_BUNDLE'] = valid_ca
    os.environ['SSL_CERT_FILE'] = valid_ca
except Exception:
    for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        val = os.environ.get(var)
        if val and not os.path.exists(val):
            os.environ.pop(var, None)

import threading
import time
from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox

# Ensure root dir is in path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller --onefile."""
    if hasattr(sys, '_MEIPASS'):
        res_path = Path(sys._MEIPASS) / relative_path
        if res_path.exists():
            return res_path
    return BASE_DIR / relative_path

import customtkinter as ctk
from PIL import Image, ImageTk
from core.config_manager import load_config, save_config, get_active_user_ids, get_base_dir
from core.state_manager import (
    load_state,
    is_file_already_sent,
    record_sent_file,
    get_next_send_epoch,
    set_next_send_epoch,
    is_folder_baselined,
    baseline_folder_contents
)
from core.file_watcher import get_latest_file
from core.bale_client import get_bot_info, broadcast_message, broadcast_document, verify_bot_token_and_username
from core.archiver import prepare_file_for_sending
from core.bale_listener import load_registered_users, BaleBotListener
from core.security_utils import validate_safe_folder, mask_token
from core.reporter import generate_5min_status_report, format_remaining_time
from core.ssl_helper import apply_ssl_fix
apply_ssl_fix()
import service_worker
from core.service_manager import (
    is_worker_running,
    start_worker_process,
    stop_worker_process,
    setup_full_autostart,
    remove_full_autostart
)
from core.license_manager import (
    is_license_active,
    request_and_send_activation_code,
    verify_and_activate,
    get_pending_request_status,
    validate_iran_phone,
    activate_plan_directly,
    notify_admin_on_activation,
    SUPER_ADMIN_ID,
    PLANS,
    DEFAULT_PLAN_ID
)
from core.gui_clipboard_helper import setup_global_clipboard_shortcuts, attach_entry_context_menu
from core.self_updater import check_and_notify_post_update, get_current_executable_path

# Set appearance theme
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

LOG_FILE = get_base_dir() / "service.log"

class ActivationDialog(ctk.CTkToplevel):
    """
    Modal activation dialog for Axis Puls software.
    Supports 3 tiers:
      1. Trial: Free 72 Hours (رایگان ۷۲ ساعته)
      2. Plan 1: 1 Year - 5 Million Tomans (۱ ساله - ۵ میلیون تومان)
      3. Plan 2: 10 Years - 20 Million Tomans (۱۰ ساله - ۲۰ میلیون تومان)
    Collects user's mobile phone number and notifies admin with activation code and requested plan.
    Enforces a strict 24-hour rate limit and requires entering the previous code on relaunch.
    """
    def __init__(self, parent, on_success: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.parent = parent
        self.on_success = on_success
        self.is_activated = False

        self.title("فعال‌سازی و انتخاب پلن اشتراک اکسیس پالس")
        self.geometry("620x760")
        self.resizable(False, False)

        # Set window icon
        icon_path = get_resource_path("app_icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # Center dialog over parent
        self.transient(parent)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.create_widgets()
        setup_global_clipboard_shortcuts(self)
        self.check_initial_pending_status()

    def create_widgets(self):
        self.configure(fg_color="#F1F5F9")
        container = ctk.CTkFrame(self, corner_radius=14, fg_color="#FFFFFF", border_color="#E2E8F0", border_width=1)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        lbl_title = ctk.CTkLabel(
            container,
            text="🔒 فعال‌سازی و صدور مجوز نرم‌افزار اکسیس پالس",
            font=ctk.CTkFont(family="Tahoma", size=16, weight="bold"),
            text_color="#0284C7"
        )
        lbl_title.pack(pady=(12, 4))

        lbl_desc = ctk.CTkLabel(
            container,
            text="جهت فعال‌سازی نرم‌افزار روی این سیستم، لطفاً ابتدا یکی از پلن‌های زیر را انتخاب نموده و شماره موبایل خود را وارد نمایید.\nکارشناسان ما تا ساعات آینده با شما تماس گرفته و کد فعال‌سازی را به شما اعلام خواهند کرد.",
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#475569",
            justify="right",
            anchor="e",
            wraplength=540
        )
        lbl_desc.pack(padx=20, fill="x", pady=(0, 8))

        # 1. Plan Selection Section
        lbl_plans = ctk.CTkLabel(
            container,
            text="⭐ ۱. پلن فعال‌سازی مورد نظر خود را انتخاب نمایید:",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        lbl_plans.pack(fill="x", padx=20, pady=(2, 4))

        self.selected_plan = ctk.StringVar(value=DEFAULT_PLAN_ID)
        self.selected_plan.trace_add("write", self.on_plan_change)

        plans_frame = ctk.CTkFrame(container, fg_color="#F8FAFC", corner_radius=10, border_color="#CBD5E1", border_width=1)
        plans_frame.pack(fill="x", padx=20, pady=(0, 8))

        # Radio 1: 72-Hour Free Trial
        self.rdo_trial = ctk.CTkRadioButton(
            plans_frame,
            text="🎁 آزمایش رایگان ۷۲ ساعته (رایگان - ۳ روز)",
            variable=self.selected_plan,
            value="trial_72h",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        self.rdo_trial.pack(anchor="e", padx=16, pady=(6, 2))

        lbl_desc_trial = ctk.CTkLabel(
            plans_frame,
            text="استفاده کامل و نامحدود به مدت ۷۲ ساعت (۳ روز) جهت ارزیابی و تست ارسال فایل",
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#64748B",
            anchor="e"
        )
        lbl_desc_trial.pack(anchor="e", padx=36, pady=(0, 4))

        # Radio 2: 1-Year (5 Million Tomans)
        self.rdo_1y = ctk.CTkRadioButton(
            plans_frame,
            text="⭐ اشتراک ۱ ساله (۵ میلیون تومان - ۳۶۵ روز)",
            variable=self.selected_plan,
            value="plan_1y",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        self.rdo_1y.pack(anchor="e", padx=16, pady=(2, 2))

        lbl_desc_1y = ctk.CTkLabel(
            plans_frame,
            text="یک سال دسترسی کامل، آپدیت‌های مداوم و پشتیبانی اختصاصی برای ۱۲ ماه",
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#64748B",
            anchor="e"
        )
        lbl_desc_1y.pack(anchor="e", padx=36, pady=(0, 4))

        # Radio 3: 10-Year (20 Million Tomans)
        self.rdo_10y = ctk.CTkRadioButton(
            plans_frame,
            text="💎 اشتراک ۱۰ ساله (۲۰ میلیون تومان - ۳۶۵۰ روز)",
            variable=self.selected_plan,
            value="plan_10y",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        self.rdo_10y.pack(anchor="e", padx=16, pady=(2, 2))

        lbl_desc_10y = ctk.CTkLabel(
            plans_frame,
            text="مجوز بلندمدت ویژه سازمان‌ها و کسب‌وکارها با تخفیف ویژه و ثبات ۱۰ ساله",
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#64748B",
            anchor="e"
        )
        lbl_desc_10y.pack(anchor="e", padx=36, pady=(0, 6))

        # 2. Mobile input card
        self.lbl_phone = ctk.CTkLabel(
            container,
            text="📱 ۲. شماره موبایل (اختیاری جهت پشتیبانی):",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        self.lbl_phone.pack(fill="x", padx=20, pady=(2, 3))

        self.entry_phone = ctk.CTkEntry(
            container,
            placeholder_text="اختیاری - مثال: 09123456789",
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color="#F8FAFC",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            height=36,
            justify="center"
        )
        self.entry_phone.pack(fill="x", padx=20, pady=(0, 6))
        attach_entry_context_menu(self.entry_phone)

        # Button 1: Request activation
        self.btn_request = ctk.CTkButton(
            container,
            text="🎁 فعال‌سازی آنی نسخه رایگان ۷۲ ساعته",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            height=36,
            command=self.on_request_clicked
        )
        self.btn_request.pack(fill="x", padx=20, pady=(2, 4))

        self.lbl_req_status = ctk.CTkLabel(
            container,
            text="نسخه آزمایشی به صورت آنی فعال خواهد شد (نیاز به تماس یا کد فعال‌سازی ندارد).",
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#059669",
            justify="center",
            wraplength=520
        )
        self.lbl_req_status.pack(pady=(0, 6))

        # Divider
        divider = ctk.CTkFrame(container, height=1, fg_color="#E2E8F0")
        divider.pack(fill="x", padx=20, pady=2)

        # 3. Code entry section
        lbl_code = ctk.CTkLabel(
            container,
            text="🔑 ۳. کد فعال‌سازی ۱۰ کاراکتری اعلام‌شده در تماس تلفنی:",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        lbl_code.pack(fill="x", padx=20, pady=(4, 3))

        self.entry_code = ctk.CTkEntry(
            container,
            placeholder_text="کد ۱۰ کاراکتری مانند 9K7X2B8M4N",
            font=ctk.CTkFont(family="Courier", size=15, weight="bold"),
            fg_color="#F8FAFC",
            border_color="#0284C7",
            border_width=2,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            height=38,
            justify="center"
        )
        self.entry_code.pack(fill="x", padx=48, pady=(0, 6))
        attach_entry_context_menu(self.entry_code)

        # Button 2: Verify & Activate
        self.btn_activate = ctk.CTkButton(
            container,
            text="✅ تأیید کد و فعال‌سازی سرویس",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            height=40,
            command=self.on_activate_clicked
        )
        self.btn_activate.pack(fill="x", padx=20, pady=(2, 4))

        self.lbl_act_status = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(family="Tahoma", size=10, weight="bold"),
            text_color="#EF4444",
            justify="center",
            wraplength=520
        )
        self.lbl_act_status.pack(pady=(0, 4))

    def check_initial_pending_status(self):
        """Checks if a request was already submitted in the last 24 hours."""
        is_pending, msg, rec = get_pending_request_status()
        if is_pending and rec:
            phone = rec.get("user_phone", "")
            pid = rec.get("plan_id", DEFAULT_PLAN_ID)
            self.selected_plan.set(pid)
            self.rdo_trial.configure(state="disabled")
            self.rdo_1y.configure(state="disabled")
            self.rdo_10y.configure(state="disabled")
            self.entry_phone.delete(0, "end")
            self.entry_phone.insert(0, phone)
            self.entry_phone.configure(state="disabled")
            self.btn_request.configure(
                state="disabled",
                text="⏳ درخواست قبلاً ثبت شده است (در انتظار تماس)",
                fg_color="#94A3B8"
            )
            self.lbl_req_status.configure(text=msg, text_color="#0284C7")
            self.entry_code.focus_set()

    def on_plan_change(self, *args):
        """Switches UI between instant 72-hour trial and paid subscription requests."""
        plan = self.selected_plan.get()
        if plan == "trial_72h":
            if hasattr(self, "lbl_phone"):
                self.lbl_phone.configure(text="📱 ۲. شماره موبایل خود را وارد نمایید (الزامی):")
            if hasattr(self, "entry_phone"):
                self.entry_phone.configure(placeholder_text="مثال: 09123456789")
            if hasattr(self, "btn_request"):
                self.btn_request.configure(
                    text="🎁 فعال‌سازی آنی نسخه رایگان ۷۲ ساعته",
                    fg_color="#10B981",
                    hover_color="#059669"
                )
            if hasattr(self, "lbl_req_status"):
                self.lbl_req_status.configure(
                    text="پس از ثبت شماره، نسخه آزمایشی فوراً فعال شده و این پنجره بسته خواهد شد.",
                    text_color="#059669"
                )
        else:
            if hasattr(self, "lbl_phone"):
                self.lbl_phone.configure(text="📱 ۲. شماره موبایل خود را وارد نمایید:")
            if hasattr(self, "entry_phone"):
                self.entry_phone.configure(placeholder_text="مثال: 09123456789")
            if hasattr(self, "btn_request"):
                self.btn_request.configure(
                    text="📞 ثبت درخواست خرید اشتراک و تماس کارشناس",
                    fg_color="#0284C7",
                    hover_color="#0369A1"
                )
            if hasattr(self, "lbl_req_status"):
                self.lbl_req_status.configure(
                    text="کارشناسان ما تا ساعات آینده جهت فعال‌سازی سیستم با شما تماس خواهند گرفت.",
                    text_color="#64748B"
                )

    def on_request_clicked(self):
        chosen_plan = self.selected_plan.get()

        phone = self.entry_phone.get().strip()
        ok_phone, phone_res = validate_iran_phone(phone)
        if not ok_phone:
            self.lbl_req_status.configure(text=phone_res, text_color="#EF4444")
            self.entry_phone.focus_set()
            return

        # 1. 72-Hour Instant Free Trial (Direct one-click activation + Bot ID SMS + HW report to Bale Admin)
        if chosen_plan == "trial_72h":
            self.btn_request.configure(state="disabled", text="⏳ در حال فعال‌سازی نسخه آزمایشی...")
            self.lbl_req_status.configure(text="در حال فعال‌سازی آنی و بستن صفحه...", text_color="#0284C7")
            threading.Thread(target=self._run_instant_trial, args=(phone_res,), daemon=True).start()
            return

        # 2. Paid Subscription Request (Sends request to Admin)
        self.btn_request.configure(state="disabled", text="⏳ در حال ثبت و ارسال درخواست...")
        self.lbl_req_status.configure(text="در حال ارسال اطلاعات درخواست به کارشناس پشتیبانی...", text_color="#0284C7")
        threading.Thread(target=self._run_request, args=(phone_res, chosen_plan), daemon=True).start()

    def _run_instant_trial(self, phone: str = ""):
        """Activates 72-hour trial directly, sends Bot ID SMS to Admin, and sends full hardware info to Admin in Bale."""
        ok, msg, lic_data = activate_plan_directly("trial_72h", activated_by="user_instant_trial", user_phone=phone)

        token = getattr(self.parent, "entry_token", None)
        token_str = token.get().strip() if token else ""
        bot_user = getattr(self.parent, "entry_bot_username", None)
        bot_user_str = bot_user.get().strip() if bot_user else ""
        if not token_str:
            token_str = self.parent.config_data.get("bot_token", "")
        if not bot_user_str:
            bot_user_str = self.parent.config_data.get("bot_username", "")

        if ok:
            notify_admin_on_activation(token_str, bot_user_str, "رایگان ۷۲ ساعته", user_phone=phone)

        self.after(0, self._handle_instant_trial_result, ok, msg)

    def _handle_instant_trial_result(self, ok: bool, msg: str):
        if ok:
            self.is_activated = True
            self.parent.on_license_activated()
            self.grab_release()
            self.destroy()
            if self.on_success:
                self.parent.after(100, self.on_success)
        else:
            self.btn_request.configure(state="normal", text="🎁 فعال‌سازی آنی نسخه رایگان ۷۲ ساعته")
            self.lbl_req_status.configure(text=msg, text_color="#EF4444")

    def _run_request(self, phone: str, plan_id: str):
        ok, msg = request_and_send_activation_code(phone, plan_id)
        self.after(0, self._handle_request_result, ok, msg, phone)

    def _handle_request_result(self, ok: bool, msg: str, phone: str):
        if ok:
            self.rdo_trial.configure(state="disabled")
            self.rdo_1y.configure(state="disabled")
            self.rdo_10y.configure(state="disabled")
            self.entry_phone.configure(state="disabled")
            self.btn_request.configure(
                state="disabled",
                text="⏳ درخواست ثبت شد (در انتظار تماس)",
                fg_color="#94A3B8"
            )
            self.lbl_req_status.configure(text=msg, text_color="#10B981")
            self.entry_code.focus_set()
        else:
            self.btn_request.configure(state="normal", text="📞 ثبت درخواست خرید اشتراک و تماس کارشناس")
            self.lbl_req_status.configure(text=msg, text_color="#EF4444")

    def on_activate_clicked(self):
        code = self.entry_code.get().strip()
        if not code:
            self.lbl_act_status.configure(text="لطفاً کد ۱۰ کاراکتری اعلام‌شده توسط کارشناس را وارد نمایید.", text_color="#EF4444")
            self.entry_code.focus_set()
            return

        self.btn_activate.configure(state="disabled", text="⏳ در حال بررسی مجوز...")
        threading.Thread(target=self._run_activate, args=(code,), daemon=True).start()

    def _run_activate(self, code: str):
        ok, msg = verify_and_activate(code)
        self.after(0, self._handle_activate_result, ok, msg)

    def _handle_activate_result(self, ok: bool, msg: str):
        self.btn_activate.configure(state="normal", text="✅ تأیید کد و فعال‌سازی سرویس")
        if ok:
            self.is_activated = True
            messagebox.showinfo("فعال‌سازی موفق", msg)
            self.parent.on_license_activated()
            self.grab_release()
            self.destroy()
            if self.on_success:
                self.parent.after(100, self.on_success)
        else:
            self.lbl_act_status.configure(text=msg, text_color="#EF4444")

    def on_close(self):
        self.grab_release()
        self.destroy()

class BaleFileSenderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("اکسیس پالس (Axis Puls) - سامانه پایش دائمی و ارسال هوشمند فایل")
        self.geometry("880x940")
        self.minsize(800, 820)
        self.configure(fg_color="#F1F5F9")

        # Set window icon
        self.set_app_icon()

        self.config_data = load_config()
        self.log_file_pos = 0
        self.is_monitoring = True
        self.gui_bot_listener = None

        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

        self.create_widgets()
        setup_global_clipboard_shortcuts(self)
        self.load_values_to_ui()

        # If token is present and worker is not running, start local listener for real-time /start responses
        init_token = self.config_data.get("bot_token", "").strip()
        if init_token:
            try:
                check_and_notify_post_update(init_token)
            except Exception:
                pass
        if init_token and not is_worker_running():
            self.start_gui_bot_listener(init_token)

        # Initialize log position to end of existing file so we only stream new events
        if LOG_FILE.exists():
            try:
                self.log_file_pos = os.path.getsize(LOG_FILE)
            except Exception:
                self.log_file_pos = 0

        # Start background timer for status updates & countdown
        self.status_thread = threading.Thread(target=self.periodic_status_checker, daemon=True)
        self.status_thread.start()

        # Start log tailer thread to mirror background service logs in real-time
        self.tailer_thread = threading.Thread(target=self.periodic_log_tailer, daemon=True)
        self.tailer_thread.start()

        # Check license activation on launch
        self.after(250, self.check_and_enforce_license)

    def check_and_enforce_license(self):
        """Checks license activation on startup and updates status badge (without opening modal dialog)."""
        active, msg, info = is_license_active()
        if not active:
            if hasattr(self, "lbl_license_badge"):
                self.lbl_license_badge.configure(text="🔒 اعتبار: منقضی شده (نیاز به تمدید)", text_color="#EF4444")
        else:
            time_rem = info.get("time_rem_str", "")
            if hasattr(self, "lbl_license_badge"):
                self.lbl_license_badge.configure(text=f"🔒 اعتبار: {time_rem} وقت داری", text_color="#10B981")

    def open_activation_dialog(self, on_success: Optional[Callable[[], None]] = None):
        """Opens modal activation dialog."""
        ActivationDialog(self, on_success=on_success)

    def open_activation_dialog_manual(self):
        """Displays license details or opens activation dialog if inactive."""
        active, msg, info = is_license_active()
        if active:
            plan_title = info.get("plan_title", "اشتراک فعال")
            plan_price = info.get("plan_price", "")
            time_rem = info.get("time_rem_str", f"{info.get('remaining_days', 0)} روز")
            exp_str = info.get("expiry_str", "نامشخص")
            act_str = info.get("activated_at", "نامشخص")
            price_line = f"• تعرفه پلن: {plan_price}\n" if plan_price else ""
            prompt_msg = (
                f"✅ نرم‌افزار روی این سیستم با موفقیت فعال شده است.\n\n"
                f"• نوع اشتراک: {plan_title}\n"
                f"{price_line}"
                f"• وضعیت مجوز: فعال و معتبر\n"
                f"• تاریخ فعال‌سازی: {act_str}\n"
                f"• تاریخ انقضای مجوز: {exp_str}\n"
                f"• مدت زمان باقی‌مانده: {time_rem} وقت داری\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"آیا مایلید کل سشن و لایسنس نرم‌افزار را ریست کنید؟\n"
                f"(با ریست، سیستم دقیقاً مانند بار اول نصب خواهد شد و نیاز به فعال‌سازی مجدد خواهد داشت)"
            )
            want_reset = messagebox.askyesno("اطلاعات مجوز و مدیریت سشن", prompt_msg)
            if want_reset:
                from core.license_manager import reset_software_session
                ok, r_msg = reset_software_session()
                if ok:
                    messagebox.showinfo("ریست موفق", r_msg)
                    if hasattr(self, "lbl_license_badge"):
                        self.lbl_license_badge.configure(text="🔒 اعتبار: منقضی شده (نیاز به تمدید)", text_color="#EF4444")
                    self.open_activation_dialog()
                else:
                    messagebox.showerror("خطا در ریست", r_msg)
        else:
            self.open_activation_dialog()

    def on_license_activated(self):
        """Callback when activation succeeds."""
        active, msg, info = is_license_active()
        plan_title = info.get("plan_title", "فعال")
        time_rem = info.get("time_rem_str", "")
        if hasattr(self, "lbl_license_badge"):
            if active:
                self.lbl_license_badge.configure(text=f"🔒 اعتبار: {time_rem} وقت داری", text_color="#10B981")
            else:
                self.lbl_license_badge.configure(text="🔒 اعتبار: منقضی شده (نیاز به تمدید)", text_color="#EF4444")
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ نرم‌افزار اکسیس پالس با موفقیت فعال شد ({plan_title} - {time_rem} وقت داری).")

    def set_app_icon(self):
        """Sets application window icon from app_icon.ico or logo-original.png."""
        icon_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("logo-original.png")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
                return
            except Exception:
                pass
        if png_path.exists():
            try:
                img = Image.open(png_path)
                self.tk_icon = ImageTk.PhotoImage(img)
                self.iconphoto(False, self.tk_icon)
            except Exception:
                pass

    def create_widgets(self):
        # Header Frame (Modern White Card with Slate Border)
        self.header_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#FFFFFF",
            border_color="#E2E8F0",
            border_width=1
        )
        self.header_frame.pack(fill="x", padx=16, pady=(12, 6))

        # Brand / Logo Banner container
        brand_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        brand_container.pack(fill="x", padx=16, pady=(12, 8))

        # Load and render logo
        logo_path = get_resource_path("logo-original.png")
        self.logo_image = None
        if logo_path.exists():
            try:
                pil_logo = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(
                    light_image=pil_logo,
                    dark_image=pil_logo,
                    size=(72, 72)
                )
                lbl_logo = ctk.CTkLabel(brand_container, image=self.logo_image, text="")
                lbl_logo.pack(side="right", padx=(12, 4))
            except Exception as e:
                print(f"Error loading logo: {e}")

        # Text banner
        text_container = ctk.CTkFrame(brand_container, fg_color="transparent")
        text_container.pack(side="right", fill="both", expand=True, padx=4)

        title_label = ctk.CTkLabel(
            text_container,
            text="اکسیس پالس | Axis Puls",
            font=ctk.CTkFont(family="Tahoma", size=20, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        title_label.pack(fill="x", pady=(2, 2))

        subtitle_label = ctk.CTkLabel(
            text_container,
            text="سامانه پایش هوشمند پوشه و ارسال خودکار فایل به پیام‌رسان بله",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
            text_color="#334155",
            anchor="e"
        )
        subtitle_label.pack(fill="x", pady=(0, 2))

        desc_label = ctk.CTkLabel(
            text_container,
            text="ارسال قطعی تک‌باره هر فایل • انتظار خودکار برای فایل جدید • پشتیبانی از فایل‌های بالای ۲۰ مگابایت با تقسیم زیپ",
            font=ctk.CTkFont(family="Tahoma", size=11),
            text_color="#64748B",
            anchor="e"
        )
        desc_label.pack(fill="x", pady=(0, 2))

        # Status & Countdown Bar Frame
        self.status_bar_frame = ctk.CTkFrame(
            self.header_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        self.status_bar_frame.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_service_status = ctk.CTkLabel(
            self.status_bar_frame,
            text="وضعیت: در حال بررسی...",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            text_color="#D97706"
        )
        self.lbl_service_status.pack(side="right", padx=12, pady=6)

        self.lbl_countdown = ctk.CTkLabel(
            self.status_bar_frame,
            text="⏱ ارسال بعدی: محاسبه...",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0284C7"
        )
        self.lbl_countdown.pack(side="right", padx=14, pady=6)

        self.lbl_license_badge = ctk.CTkLabel(
            self.status_bar_frame,
            text="🔒 مجوز: در حال بررسی...",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#64748B"
        )
        self.lbl_license_badge.pack(side="left", padx=10, pady=6)

        self.lbl_last_sent = ctk.CTkLabel(
            self.status_bar_frame,
            text="آخرین ارسال: هیچ",
            font=ctk.CTkFont(family="Tahoma", size=11),
            text_color="#64748B"
        )
        self.lbl_last_sent.pack(side="left", padx=8, pady=6)

        # Main Scrollable Form Frame
        self.main_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#FFFFFF",
            border_color="#E2E8F0",
            border_width=1
        )
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=4)

        # Section 1: Folder Selection
        sec1_title = ctk.CTkLabel(
            self.main_frame,
            text="📁 ۱. انتخاب پوشه تحت نظارت",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        sec1_title.pack(fill="x", padx=10, pady=(8, 3))

        folder_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        folder_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_browse = ctk.CTkButton(
            folder_frame,
            text="انتخاب پوشه...",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            width=110,
            height=34,
            command=self.browse_folder
        )
        self.btn_browse.pack(side="left", padx=8, pady=8)

        self.entry_folder = ctk.CTkEntry(
            folder_frame,
            placeholder_text="مسیر پوشه هدف را انتخاب کنید...",
            font=ctk.CTkFont(family="Tahoma", size=11),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            height=34
        )
        self.entry_folder.pack(side="right", fill="x", expand=True, padx=8, pady=8)
        attach_entry_context_menu(self.entry_folder)

        # Section 2: Bale Bot Token & Guided Onboarding
        sec2_title = ctk.CTkLabel(
            self.main_frame,
            text="🤖 ۲. مشخصات و راه‌اندازی بازو در بله (Bot Token)",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        sec2_title.pack(fill="x", padx=10, pady=(6, 3))

        token_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        token_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Visual Step-by-Step Onboarding Guide
        guide_box = ctk.CTkFrame(
            token_frame,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_color="#CBD5E1",
            border_width=1
        )
        guide_box.pack(fill="x", padx=10, pady=(8, 8))

        guide_header = ctk.CTkLabel(
            guide_box,
            text="📋 راهنمای گام‌به‌گام راه‌اندازی و اتصال بازو (Bot) در بله:",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0284C7",
            anchor="e"
        )
        guide_header.pack(fill="x", padx=12, pady=(6, 2))

        guide_steps = (
            "۱. در پیام‌رسان بله وارد ربات رسمی botfather@ شده و احراز هویت خود را تکمیل فرمایید.\n"
            "۲. دستور newbot/ را ارسال کرده و نام و شناسه‌ای دلخواه برای بازوی خود تعیین کنید.\n"
            "۳. آیدی (شناسه) و توکن بازوی ساخته‌شده را در کادرهای زیر وارد نمایید.\n"
            "۴. روی دکمه «⚡ استعلام و راه‌اندازی ربات» کلیک کنید تا بازوی شما استعلام، تأیید و آنلاین شود.\n"
            "۵. اکنون خودتان یا کاربران، وارد ربات شده و دکمه start/ را بزنید تا شناسه عددی شما ارسال گردد.\n"
            "۶. شناسه عددی دریافتی را در بخش ۳ ثبت نمایید (یا دکمه بازیابی خودکار را بزنید)."
        )
        lbl_guide = ctk.CTkLabel(
            guide_box,
            text=guide_steps,
            font=ctk.CTkFont(family="Tahoma", size=10),
            text_color="#334155",
            justify="right",
            anchor="e"
        )
        lbl_guide.pack(fill="x", padx=12, pady=(0, 8))

        # Bot username input row
        uname_row = ctk.CTkFrame(token_frame, fg_color="transparent")
        uname_row.pack(fill="x", padx=10, pady=(0, 6))

        lbl_uname_title = ctk.CTkLabel(
            uname_row,
            text="شناسه / آیدی بازو (Bot ID):",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#1E293B",
            anchor="e",
            width=170
        )
        lbl_uname_title.pack(side="right", padx=(8, 0))

        self.entry_bot_username = ctk.CTkEntry(
            uname_row,
            placeholder_text="مثال: my_backup_bot@ یا my_backup_bot (جهت استعلام تطابق با توکن)",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            height=34
        )
        self.entry_bot_username.pack(side="right", fill="x", expand=True)
        attach_entry_context_menu(self.entry_bot_username)

        # Token input row with activation button
        token_row = ctk.CTkFrame(token_frame, fg_color="transparent")
        token_row.pack(fill="x", padx=10, pady=(0, 4))

        self.btn_activate_bot = ctk.CTkButton(
            token_row,
            text="⚡ استعلام و راه‌اندازی ربات",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            width=180,
            height=34,
            command=self.activate_bot_threaded
        )
        self.btn_activate_bot.pack(side="left", padx=(0, 8))

        self.entry_token = ctk.CTkEntry(
            token_row,
            placeholder_text="توکن دریافتی از BotFather بله را اینجا وارد کنید...",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            height=34
        )
        self.entry_token.pack(side="right", fill="x", expand=True)
        attach_entry_context_menu(self.entry_token)

        self.lbl_bot_status = ctk.CTkLabel(
            token_frame,
            text="",
            font=ctk.CTkFont(family="Tahoma", size=11),
            text_color="#64748B",
            anchor="e",
            wraplength=760,
            justify="right"
        )
        self.lbl_bot_status.pack(fill="x", padx=12, pady=(0, 6))

        # Section 3: Three User IDs & Auto-fetch
        sec3_title = ctk.CTkLabel(
            self.main_frame,
            text="👥 ۳. شناسه‌های عددی ۳ کاربر دریافت‌کننده فایل",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
            text_color="#0F172A",
            anchor="e"
        )
        sec3_title.pack(fill="x", padx=10, pady=(6, 2))

        sec3_hint = ctk.CTkLabel(
            self.main_frame,
            text="💡 راهنما: وقتی کاربری در بله به ربات شما /start بفرستد، ربات خودکار آیدی عددی‌اش را برایش ارسال می‌کند.",
            font=ctk.CTkFont(family="Tahoma", size=11),
            text_color="#0284C7",
            anchor="e"
        )
        sec3_hint.pack(fill="x", padx=10, pady=(0, 6))

        users_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        users_frame.pack(fill="x", padx=10, pady=(0, 8))

        # User 1
        u1_label = ctk.CTkLabel(users_frame, text="آیدی عددی کاربر اول (اصلی):", font=ctk.CTkFont(family="Tahoma", size=11), text_color="#334155")
        u1_label.grid(row=0, column=1, padx=(5, 12), pady=6, sticky="e")
        self.entry_user1 = ctk.CTkEntry(
            users_frame,
            placeholder_text="مثال: 1234567890",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            width=260,
            height=32,
            justify="center"
        )
        self.entry_user1.grid(row=0, column=0, padx=(12, 5), pady=6, sticky="ew")
        attach_entry_context_menu(self.entry_user1)

        # User 2
        u2_label = ctk.CTkLabel(users_frame, text="آیدی عددی کاربر دوم (اختیاری):", font=ctk.CTkFont(family="Tahoma", size=11), text_color="#334155")
        u2_label.grid(row=1, column=1, padx=(5, 12), pady=6, sticky="e")
        self.entry_user2 = ctk.CTkEntry(
            users_frame,
            placeholder_text="اختیاری",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            width=260,
            height=32,
            justify="center"
        )
        self.entry_user2.grid(row=1, column=0, padx=(12, 5), pady=6, sticky="ew")
        attach_entry_context_menu(self.entry_user2)

        # User 3
        u3_label = ctk.CTkLabel(users_frame, text="آیدی عددی کاربر سوم (اختیاری):", font=ctk.CTkFont(family="Tahoma", size=11), text_color="#334155")
        u3_label.grid(row=2, column=1, padx=(5, 12), pady=6, sticky="e")
        self.entry_user3 = ctk.CTkEntry(
            users_frame,
            placeholder_text="اختیاری",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            placeholder_text_color="#94A3B8",
            width=260,
            height=32,
            justify="center"
        )
        self.entry_user3.grid(row=2, column=0, padx=(12, 5), pady=6, sticky="ew")
        attach_entry_context_menu(self.entry_user3)

        users_frame.columnconfigure(0, weight=1)
        users_frame.columnconfigure(1, weight=1)

        fetch_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        fetch_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_auto_fill = ctk.CTkButton(
            fetch_frame,
            text="🔄 بازیابی و پرکردن آیدی کاربرانی که استارت زده‌اند",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            fg_color="#E2E8F0",
            hover_color="#CBD5E1",
            text_color="#1E293B",
            height=30,
            command=self.auto_fill_started_users
        )
        self.btn_auto_fill.pack(fill="x", padx=10, pady=6)

        # Section 4: Timer & Options
        opts_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_color="#E2E8F0",
            border_width=1
        )
        opts_frame.pack(fill="x", padx=10, pady=(0, 10))

        timer_label = ctk.CTkLabel(
            opts_frame,
            text="بازه زمانی اصلی ارسال:",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#334155"
        )
        timer_label.pack(side="right", padx=(10, 14), pady=8)

        self.combo_interval = ctk.CTkComboBox(
            opts_frame,
            values=["5 دقیقه", "10 دقیقه", "15 دقیقه (پیش‌فرض)", "30 دقیقه", "60 دقیقه"],
            font=ctk.CTkFont(family="Tahoma", size=11),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            button_color="#E2E8F0",
            button_hover_color="#CBD5E1",
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color="#0F172A",
            dropdown_hover_color="#F1F5F9",
            width=160,
            height=30
        )
        self.combo_interval.set("15 دقیقه (پیش‌فرض)")
        self.combo_interval.pack(side="right", padx=5, pady=8)

        self.chk_autostart = ctk.CTkCheckBox(
            opts_frame,
            text="فعال ماندن دائمی (اجرای خودکار هنگام روشن شدن کامپیوتر)",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            checkmark_color="#FFFFFF"
        )
        self.chk_autostart.select()
        self.chk_autostart.pack(side="left", padx=14, pady=8)

        # Row 4.2: High Compression & Data Saver Options
        opts_frame2 = ctk.CTkFrame(self, fg_color="#F8FAFC", corner_radius=10, border_color="#E2E8F0", border_width=1)
        opts_frame2.pack(fill="x", padx=16, pady=(0, 10))

        comp_label = ctk.CTkLabel(
            opts_frame2,
            text="حالت فشرده‌سازی زیپ:",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#334155"
        )
        comp_label.pack(side="right", padx=(10, 14), pady=8)

        self.combo_compression = ctk.CTkComboBox(
            opts_frame2,
            values=[
                "حداکثر استاندارد (Deflate 9 - سازگار با همه سیستم‌ها)",
                "فوق‌العاده / اولترا (LZMA Ultra - بیشترین کاهش حجم)"
            ],
            font=ctk.CTkFont(family="Tahoma", size=11),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            button_color="#E2E8F0",
            button_hover_color="#CBD5E1",
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color="#0F172A",
            dropdown_hover_color="#F1F5F9",
            width=275,
            height=30
        )
        self.combo_compression.set("حداکثر استاندارد (Deflate 9 - سازگار با همه سیستم‌ها)")
        self.combo_compression.pack(side="right", padx=5, pady=8)

        self.chk_auto_compress = ctk.CTkCheckBox(
            opts_frame2,
            text="فشرده‌سازی خودکار قبل از ارسال (کاهش چشمگیر مصرف اینترنت)",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color="#0F172A",
            checkmark_color="#FFFFFF"
        )
        self.chk_auto_compress.pack(side="left", padx=14, pady=8)

        # Section 5: Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=4)

        self.btn_save = ctk.CTkButton(
            btn_frame,
            text="💾 ذخیره و شروع سرویس",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            height=38,
            command=self.save_and_start_service
        )
        self.btn_save.pack(side="right", fill="x", expand=True, padx=2)

        self.btn_report_now = ctk.CTkButton(
            btn_frame,
            text="🔍 گزارش وضعیت فوری",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            text_color="#FFFFFF",
            height=38,
            command=self.show_instant_report_threaded
        )
        self.btn_report_now.pack(side="right", fill="x", expand=True, padx=2)

        self.btn_test = ctk.CTkButton(
            btn_frame,
            text="✉️ تست ارتباط با بله",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#6366F1",
            hover_color="#4F46E5",
            text_color="#FFFFFF",
            height=38,
            command=self.test_connection_threaded
        )
        self.btn_test.pack(side="right", fill="x", expand=True, padx=2)

        self.btn_check_now = ctk.CTkButton(
            btn_frame,
            text="⚡ ارسال فایل همین الان",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#F59E0B",
            hover_color="#D97706",
            text_color="#FFFFFF",
            height=38,
            command=self.check_and_send_now_threaded
        )
        self.btn_check_now.pack(side="right", fill="x", expand=True, padx=2)

        self.btn_send_latest_version = ctk.CTkButton(
            btn_frame,
            text="📤 ارسال آخرین نسخه",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            text_color="#FFFFFF",
            height=38,
            command=self.send_latest_version_threaded
        )
        self.btn_send_latest_version.pack(side="right", fill="x", expand=True, padx=2)

        self.btn_stop = ctk.CTkButton(
            btn_frame,
            text="⏹ توقف",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#EF4444",
            hover_color="#DC2626",
            text_color="#FFFFFF",
            width=65,
            height=38,
            command=self.stop_service
        )
        self.btn_stop.pack(side="right", fill="x", expand=False, padx=2)

        self.btn_license = ctk.CTkButton(
            btn_frame,
            text="🔑 مجوز",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            fg_color="#64748B",
            hover_color="#475569",
            text_color="#FFFFFF",
            width=65,
            height=38,
            command=self.open_activation_dialog_manual
        )
        self.btn_license.pack(side="right", fill="x", expand=False, padx=2)

        # Section 6: Real-time Log & Report Box Toolbar
        log_bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_bar_frame.pack(fill="x", padx=16, pady=(4, 2))

        log_header = ctk.CTkLabel(
            log_bar_frame,
            text="📋 لیست گزارش‌ها، وضعیت ۵ دقیقه‌ای و لاگ لحظه‌ای:",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
            text_color="#475569",
            anchor="e"
        )
        log_header.pack(side="right", padx=4)

        self.btn_clear_log = ctk.CTkButton(
            log_bar_frame,
            text="🗑 پاک کردن",
            font=ctk.CTkFont(family="Tahoma", size=11),
            fg_color="#E2E8F0",
            hover_color="#CBD5E1",
            text_color="#334155",
            width=75,
            height=26,
            command=self.clear_log
        )
        self.btn_clear_log.pack(side="left", padx=4)

        self.btn_copy_all = ctk.CTkButton(
            log_bar_frame,
            text="📋 کپی کل گزارشات",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            fg_color="#E2E8F0",
            hover_color="#CBD5E1",
            text_color="#0284C7",
            width=125,
            height=26,
            command=self.copy_all_log
        )
        self.btn_copy_all.pack(side="left", padx=4)

        self.txt_log = ctk.CTkTextbox(
            self,
            height=140,
            font=ctk.CTkFont(family="Tahoma", size=10),
            fg_color="#FFFFFF",
            border_color="#CBD5E1",
            border_width=1,
            text_color="#0F172A",
            corner_radius=8
        )
        self.txt_log.pack(fill="both", padx=16, pady=(0, 10))

        # Enable free selection and copying while blocking keyboard modifications
        self.setup_log_copying_and_context_menu()

        self.append_log("سامانه پایش آماده است. هر ۵ دقیقه گزارش جامع بررسی فایل و زمان باقی‌مانده تا ارسال ثبت می‌شود.")

    def setup_log_copying_and_context_menu(self):
        """Allows mouse text selection and right-click copying while preventing accidental edits."""
        inner_txt = self.txt_log._textbox

        def _prevent_typing(event):
            # Allow Ctrl+C (Copy), Ctrl+A (Select All), navigation
            if (event.state & 4) and event.keysym.lower() in ('c', 'a', 'insert'):
                return None
            if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Prior', 'Next', 'Home', 'End'):
                return None
            # Block edits
            return "break"

        inner_txt.bind("<Key>", _prevent_typing)

        # Context menu
        import tkinter as tk
        self.log_menu = tk.Menu(self, tearoff=0, font=("Tahoma", 10), bg="#FFFFFF", fg="#0F172A", activebackground="#F1F5F9", activeforeground="#0284C7")
        self.log_menu.add_command(label="📋 کپی متن انتخاب‌شده", command=self.copy_selected_log)
        self.log_menu.add_command(label="📑 انتخاب همه متن", command=self.select_all_log)
        self.log_menu.add_command(label="💾 کپی تمام متن گزارشات", command=self.copy_all_log)
        self.log_menu.add_separator()
        self.log_menu.add_command(label="🗑 پاک کردن گزارشات", command=self.clear_log)

        def _show_context_menu(event):
            try:
                self.log_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.log_menu.grab_release()

        inner_txt.bind("<Button-3>", _show_context_menu)

    def copy_selected_log(self):
        """Copies highlighted text to clipboard."""
        try:
            sel = self.txt_log._textbox.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
                self.update()
        except Exception:
            pass

    def select_all_log(self):
        """Selects all text in the report box."""
        self.txt_log._textbox.tag_add("sel", "1.0", "end")

    def copy_all_log(self):
        """Copies entire report log to system clipboard."""
        content = self.txt_log.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showinfo("اطلاع", "متنی در بخش گزارشات برای کپی وجود ندارد.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        messagebox.showinfo("موفقیت", "متن تمام گزارشات با موفقیت در کلیپ‌بورد کپی شد.")

    def clear_log(self):
        """Clears the log box."""
        self.txt_log.delete("1.0", "end")

    def append_log(self, text: str):
        """Appends text to UI log box safely on the main Tkinter thread."""
        if not getattr(self, "is_monitoring", False):
            return
        try:
            self.after(0, self._safe_append_log, text)
        except Exception:
            pass

    def _safe_append_log(self, text: str):
        try:
            self.txt_log.insert("end", text.rstrip() + "\n")
            self.txt_log.see("end")
        except Exception:
            pass

    def periodic_log_tailer(self):
        """Monitors service.log file and streams new lines directly to UI textbox."""
        while self.is_monitoring:
            try:
                if LOG_FILE.exists():
                    current_size = os.path.getsize(LOG_FILE)
                    if current_size > self.log_file_pos:
                        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self.log_file_pos)
                            new_content = f.read()
                            self.log_file_pos = f.tell()
                            if new_content:
                                self.append_log(new_content)
                    elif current_size < self.log_file_pos:
                        # Log was rotated/truncated
                        self.log_file_pos = 0
            except Exception:
                pass
            time.sleep(1.5)

    def browse_folder(self):
        curr = self.entry_folder.get().strip() or str(get_base_dir())
        chosen = filedialog.askdirectory(initialdir=curr, title="پوشه ارسال فایل را انتخاب کنید")
        if chosen:
            self.entry_folder.delete(0, "end")
            self.entry_folder.insert(0, os.path.normpath(chosen))
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] پوشه انتخاب شد: {chosen}")

    def load_values_to_ui(self):
        cfg = self.config_data
        if cfg.get("folder_path"):
            self.entry_folder.insert(0, cfg["folder_path"])
        if cfg.get("bot_username"):
            self.entry_bot_username.insert(0, cfg["bot_username"])
        if cfg.get("bot_token"):
            self.entry_token.insert(0, cfg["bot_token"])
            self.lbl_bot_status.configure(
                text="ℹ️ اطلاعات ربات از قبل بارگذاری شده است. جهت استعلام مجدد، روی دکمه استعلام و راه‌اندازی کلیک کنید.",
                text_color="#64748B"
            )

        uids = cfg.get("user_ids", ["", "", ""])
        if len(uids) > 0 and uids[0]:
            self.entry_user1.insert(0, str(uids[0]))
        if len(uids) > 1 and uids[1]:
            self.entry_user2.insert(0, str(uids[1]))
        if len(uids) > 2 and uids[2]:
            self.entry_user3.insert(0, str(uids[2]))

        mins = cfg.get("interval_minutes", 15)
        for val in self.combo_interval.cget("values"):
            if str(mins) in val:
                self.combo_interval.set(val)
                break

        if cfg.get("autostart_enabled", True):
            self.chk_autostart.select()
        else:
            self.chk_autostart.deselect()

        comp_mode = cfg.get("compression_mode", "deflate_max")
        if comp_mode == "lzma_ultra":
            self.combo_compression.set("فوق‌العاده / اولترا (LZMA Ultra - بیشترین کاهش حجم)")
        else:
            self.combo_compression.set("حداکثر استاندارد (Deflate 9 - سازگار با همه سیستم‌ها)")

        if cfg.get("auto_compress_all", False):
            self.chk_auto_compress.select()
        else:
            self.chk_auto_compress.deselect()

    def auto_fill_started_users(self):
        started_users = load_registered_users()
        if not started_users:
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] هنوز هیچ کاربری ربات را استارت نکرده است.")
            messagebox.showinfo("اطلاع", "هنوز کاربری ربات را در بله استارت نکرده است.\nکافی است کاربر به ربات شما /start بفرستد تا آیدی او ثبت شود.")
            return

        entries = [self.entry_user1, self.entry_user2, self.entry_user3]
        filled = 0
        for idx, u in enumerate(started_users[:3]):
            uid = str(u.get("user_id"))
            fname = u.get("first_name", "")
            entries[idx].delete(0, "end")
            entries[idx].insert(0, uid)
            filled += 1
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] آیدی {uid} ({fname}) در فیلد کاربر {idx+1} قرار گرفت.")

        messagebox.showinfo("موفقیت", f"تعداد {filled} آیدی از کاربرانی که اخیراً ربات را استارت کرده بودند بارگذاری شد.")

    def get_ui_config(self) -> dict:
        interval_str = self.combo_interval.get()
        mins = 15
        try:
            mins = int(''.join(filter(str.isdigit, interval_str)))
        except Exception:
            mins = 15

        comp_val = self.combo_compression.get()
        comp_mode = "lzma_ultra" if "LZMA" in comp_val else "deflate_max"

        return {
            "folder_path": self.entry_folder.get().strip(),
            "bot_token": self.entry_token.get().strip(),
            "bot_username": self.entry_bot_username.get().strip(),
            "user_ids": [
                self.entry_user1.get().strip(),
                self.entry_user2.get().strip(),
                self.entry_user3.get().strip()
            ],
            "interval_minutes": mins,
            "autostart_enabled": bool(self.chk_autostart.get()),
            "compression_mode": comp_mode,
            "auto_compress_all": bool(self.chk_auto_compress.get())
        }

    def save_and_start_service(self):
        cfg = self.get_ui_config()
        is_valid, msg, safe_path = validate_safe_folder(cfg["folder_path"])
        if not is_valid:
            messagebox.showwarning("خطا", f"خطای پوشه: {msg}")
            return

        if not cfg["bot_username"]:
            messagebox.showwarning("خطا", "لطفاً شناسه / آیدی ربات (Username) بله را وارد نمایید (مثال: my_bot@).")
            self.entry_bot_username.focus_set()
            return

        if not cfg["bot_token"]:
            messagebox.showwarning("خطا", "لطفاً توکن ربات بله را وارد فرمایید.")
            self.entry_token.focus_set()
            return

        # Inquiry bot token and username from Bale
        ok_bot, bot_msg, bot_data = verify_bot_token_and_username(cfg["bot_token"], cfg["bot_username"])
        if not ok_bot:
            messagebox.showerror("عدم تطابق یا خطای ربات بله", bot_msg)
            return

        active_users = get_active_user_ids(cfg)
        if not active_users:
            messagebox.showwarning("خطا", "حداقل باید آیدی عددی یک کاربر معتبر را وارد کنید.")
            return

        # Check license activation status
        active, lic_msg, info = is_license_active()
        if not active:
            messagebox.showwarning(
                "نیاز به فعال‌سازی نرم‌افزار",
                "نرم‌افزار هنوز روی این سیستم فعال‌سازی نشده است یا مهلت آن به پایان رسیده است.\n\n"
                "جهت راه‌اندازی و شروع سرویس پایش، لطفاً ابتدا یکی از پلن‌های فعال‌سازی (رایگان ۷۲ ساعته، ۱ ساله یا ۱۰ ساله) را انتخاب و فعال فرمایید."
            )
            ActivationDialog(self, on_success=lambda: self._continue_save_and_start(cfg))
            return

        self._continue_save_and_start(cfg)

    def _continue_save_and_start(self, cfg: dict):
        save_config(cfg)
        self.config_data = cfg
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] تنظیمات با موفقیت ذخیره شد.")

        # Baseline the folder if it has not been baselined yet so existing files are NOT sent
        folder_raw = cfg.get("folder_path", "").strip()
        is_val, _, safe_p = validate_safe_folder(folder_raw)
        if is_val:
            folder_str = str(safe_p)
            if not is_folder_baselined(folder_str):
                base_f = baseline_folder_contents(folder_str)
                if base_f:
                    self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 📂 فایل‌های از قبل موجود در پوشه (شامل «{base_f['name']}») نادیده گرفته شدند. سیستم منتظر ورود فایل جدید بعدی خواهد ماند.")
                else:
                    self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 📂 پوشه در حال حاضر خالی است. سیستم منتظر ورود اولین فایل جدید می‌باشد.")

        if cfg["autostart_enabled"]:
            ok, msg = setup_full_autostart()
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] راه‌اندازی خودکار سیستم: {msg}")
        else:
            remove_full_autostart()
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] راه‌اندازی خودکار غیرفعال شد.")

        # Stop in-app listener so background worker has exclusive access
        if hasattr(self, "gui_bot_listener") and self.gui_bot_listener:
            try:
                self.gui_bot_listener.stop()
            except Exception:
                pass

        # Start worker process
        if start_worker_process():
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] سرویس پایش پس‌زمینه با موفقیت استارت شد.")
            messagebox.showinfo(
                "موفقیت",
                "سرویس پایش خودکار با موفقیت فعال گردید.\n\n"
                "• فایل‌های از قبل موجود در پوشه ارسال نمی‌شوند و نادیده گرفته شدند.\n"
                "• سیستم منتظر ورود فایل‌های جدید بعدی می‌ماند و فقط آن‌ها را ارسال می‌کند.\n"
                "• هر فایل جدید فقط یک بار ارسال می‌شود و پس از تکمیل ارسال، منتظر فایل بعدی خواهد ماند."
            )
        else:
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] خطا در راه‌اندازی پردازش پس‌زمینه.")

    def stop_service(self):
        stop_worker_process()
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] سرویس پس‌زمینه متوقف شد.")
        messagebox.showinfo("اطلاع", "سرویس پس‌زمینه متوقف گردید.")

    def show_instant_report_threaded(self):
        threading.Thread(target=self._run_instant_report, daemon=True).start()

    def _run_instant_report(self):
        cfg = self.get_ui_config()
        folder = cfg["folder_path"]
        active_users = get_active_user_ids(cfg)
        interval_mins = cfg["interval_minutes"]
        next_epoch = get_next_send_epoch()
        if next_epoch <= 0:
            next_epoch = time.time() + interval_mins * 60

        report = generate_5min_status_report(
            folder,
            len(active_users),
            next_epoch,
            interval_mins
        )
        self.append_log("\n" + report["report_text"] + "\n")

    def activate_bot_threaded(self):
        """Inquires and validates token and bot username, tests Bale connection, and connects in-app bot listener."""
        token = self.entry_token.get().strip()
        bot_username = self.entry_bot_username.get().strip()

        if not token:
            self.lbl_bot_status.configure(
                text="❌ لطفاً ابتدا توکن دریافتی از BotFather بله را در کادر بالا وارد فرمایید.",
                text_color="#EF4444"
            )
            self.entry_token.focus_set()
            return

        if not bot_username:
            self.lbl_bot_status.configure(
                text="❌ لطفاً شناسه / آیدی بازو (Username) مانند my_bot@ را نیز وارد فرمایید تا استعلام گردد.",
                text_color="#EF4444"
            )
            self.entry_bot_username.focus_set()
            return

        self.btn_activate_bot.configure(state="disabled", text="⏳ در حال استعلام...")
        self.lbl_bot_status.configure(text="در حال استعلام توکن و تطبیق آیدی با سرور بله...", text_color="#0284C7")
        threading.Thread(target=self._run_activate_bot, args=(token, bot_username), daemon=True).start()

    def _run_activate_bot(self, token: str, bot_username: str):
        ok, msg, bot_data = verify_bot_token_and_username(token, bot_username)
        self.after(0, self._handle_activate_bot_result, ok, msg, bot_data, token, bot_username)

    def _handle_activate_bot_result(self, ok: bool, msg: str, bot_data: dict, token: str, bot_username: str):
        self.btn_activate_bot.configure(state="normal", text="⚡ استعلام و راه‌اندازی ربات")
        if ok:
            bot_name = bot_data.get("first_name", "بازوی بله")
            uname = bot_data.get("username", "")
            bot_display = f"{bot_name} (@{uname})" if uname else bot_name

            # Save token and username to configuration
            self.config_data["bot_token"] = token
            self.config_data["bot_username"] = bot_username
            save_config(self.config_data)

            # Start listener immediately so /start gets answered right away
            self.start_gui_bot_listener(token)

            success_text = f"✅ استعلام موفق: بازوی «{bot_display}» تایید و آنلاین شد! هم‌اکنون وارد ربات شده و /start را بزنید."
            self.lbl_bot_status.configure(text=success_text, text_color="#10B981")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] {success_text}")
            messagebox.showinfo(
                "استعلام و فعال‌سازی موفق بازو در بله",
                f"بازوی «{bot_display}» با موفقیت تایید و متصل گردید!\n\n"
                f"اکنون می‌توانید در پیام‌رسان بله وارد ربات خود (@{uname}) شوید و دستور /start را ارسال فرمایید تا شناسه عددی شما ارسال گردد."
            )
        else:
            err_text = f"❌ {msg}"
            self.lbl_bot_status.configure(text=err_text, text_color="#EF4444")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] {err_text}")
            messagebox.showerror("خطای استعلام ربات بله", msg)

    def start_gui_bot_listener(self, token: str):
        """Starts or restarts in-app listener so bot responds to /start even before full background service starts."""
        if hasattr(self, "gui_bot_listener") and self.gui_bot_listener:
            try:
                self.gui_bot_listener.stop()
            except Exception:
                pass

        def _on_user_started(user_info: dict):
            uid = user_info.get("user_id")
            uname = user_info.get("first_name", "") or user_info.get("username", "")
            self.after(0, self._on_user_started_in_gui, uid, uname)

        self.gui_bot_listener = BaleBotListener(token, on_user_start=_on_user_started)
        self.gui_bot_listener.start()

    def _on_user_started_in_gui(self, user_id: int, user_name: str):
        now_s = datetime.now().strftime("%H:%M:%S")
        self.append_log(f"[{now_s}] 🔔 کاربر «{user_name}» (شناسه عددی: {user_id}) ربات را در بله استارت کرد.")
        # If user 1 entry is empty, auto-populate it
        if not self.entry_user1.get().strip():
            self.entry_user1.delete(0, "end")
            self.entry_user1.insert(0, str(user_id))
            self.append_log(f"[{now_s}] 💡 شناسه عددی {user_id} به طور خودکار در فیلد کاربر اول درج گردید.")

    def on_app_close(self):
        """Safely stops listener and cleans up on main window close."""
        self.is_monitoring = False
        if hasattr(self, "gui_bot_listener") and self.gui_bot_listener:
            try:
                self.gui_bot_listener.stop()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def test_connection_threaded(self):
        threading.Thread(target=self._run_test_connection, daemon=True).start()

    def _run_test_connection(self):
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] در حال تست ارتباط با ربات بله...")
        cfg = self.get_ui_config()
        token = cfg["bot_token"]
        if not token:
            self.append_log("خطا: توکن وارد نشده است.")
            return

        ok, msg, info = get_bot_info(token)
        if not ok:
            self.append_log(f"❌ {msg}")
            return
        self.append_log(f"✅ {msg}")

        active_users = get_active_user_ids(cfg)
        if not active_users:
            self.append_log("⚠️ هیچ آیدی عددی برای ارسال پیام تست مشخص نشده است.")
            return

        test_msg = "سلام! ارتباط نرم‌افزار پایش فایل با حساب بله شما برقرار شد. فایل‌ها از این پس به صورت خودکار برای شما ارسال خواهند شد."
        res = broadcast_message(token, active_users, test_msg)
        for uid, (sent, res_msg) in res.items():
            if sent:
                self.append_log(f"✅ پیام تست به کاربر {uid} ارسال شد.")
            else:
                self.append_log(f"❌ ارسال تست به کاربر {uid} ناموفق بود: {res_msg}")

    def check_and_send_now_threaded(self):
        threading.Thread(target=self._run_check_and_send_now, daemon=True).start()

    def send_latest_version_threaded(self):
        """Uploads the latest executable file to Bale bot for admin and active users."""
        threading.Thread(target=self._run_send_latest_version, daemon=True).start()

    def _run_send_latest_version(self):
        token = self.entry_token.get().strip()
        if not token:
            self.append_log("⚠️ خطا: لطفاً ابتدا توکن ربات بله را در نرم‌افزار وارد فرمایید.")
            return

        from core.setup_sender import send_application_setup
        from core.license_manager import SUPER_ADMIN_ID

        targets = [str(SUPER_ADMIN_ID)]
        u1 = self.entry_user1.get().strip()
        if u1 and u1 not in targets:
            targets.append(u1)

        ok, msg = send_application_setup(
            token,
            targets,
            log_callback=self.append_log
        )
        if ok:
            self.append_log(f"🎉 {msg}")
        else:
            self.append_log(f"❌ {msg}")

    def _run_check_and_send_now(self):
        cfg = self.get_ui_config()
        is_valid, msg, safe_path = validate_safe_folder(cfg["folder_path"])
        if not is_valid:
            self.append_log(f"خطا: {msg}")
            return

        folder = str(safe_path)
        token = cfg["bot_token"]
        active_users = get_active_user_ids(cfg)

        if not token or not active_users:
            self.append_log("خطا: توکن یا آیدی کاربران معتبر نیست.")
            return

        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] در حال بررسی دستی پوشه: {folder} ...")
        latest = get_latest_file(folder)
        if not latest:
            self.append_log("هیچ فایلی در پوشه یافت نشد.")
            return

        self.append_log(f"آخرین فایل شناسایی شد: {latest['name']} ({latest['readable_size']})")
        if is_file_already_sent(latest):
            self.append_log(f"ℹ️ توجه: این فایل در تاریخچه ارسال‌های خودکار ثبت شده بود، اما به درخواست شما اکنون مجدداً ارسال دستی می‌شود...")
        else:
            self.append_log(f"🚀 در حال ارسال فایل به کاربران...")

        temp_dir = get_base_dir() / "temp_parts_manual"
        try:
            comp_mode = cfg.get("compression_mode", "deflate_max")
            auto_comp = cfg.get("auto_compress_all", False)
            prep_result = prepare_file_for_sending(
                latest["path"],
                str(temp_dir),
                compression_method=comp_mode,
                auto_compress_all=auto_comp
            )
            parts = prep_result["parts"]
            total_parts = len(parts)

            if prep_result["is_split"]:
                self.append_log(f"حجم بیش از ۲۰ مگابایت است. تقسیم به {total_parts} پارت زیپ...")
            elif prep_result.get("was_compressed"):
                self.append_log(f"فایل با موفقیت فشرده‌سازی شد.")

            all_parts_success = True
            for part in parts:
                p_num = part["part_number"]
                caption = (
                    f"📎 فایل جدید شناسایی شد\n"
                    f"🏷 نام اصلی: {latest['name']}\n"
                    f"📊 حجم اصلی: {latest['readable_size']}\n"
                    f"🕒 تاریخ: {latest['formatted_mtime']}\n"
                )
                if prep_result["is_split"]:
                    caption += f"📦 پارت {p_num} از {total_parts}\n{part.get('caption_note', '')}\n"
                caption += "🤖 ارسال دستی توسط کاربر"

                self.append_log(f"در حال ارسال {part['filename']} به {len(active_users)} کاربر...")
                res = broadcast_document(token, active_users, part["path"], caption, log_callback=self.append_log)
                for uid, (ok, r_msg) in res.items():
                    if ok:
                        self.append_log(f"✅ پارت {p_num} به کاربر {uid} ارسال شد.")
                    else:
                        all_parts_success = False
                        self.append_log(f"❌ ارسال پارت {p_num} به کاربر {uid} ناموفق: {r_msg}")
                        if total_parts > 1:
                            self.append_log(f"⛔ ارسال سایر پارت‌ها متوقف شد.")
                        break

            if all_parts_success:
                record_sent_file(latest)
                self.append_log(f"✅ فایل «{latest['name']}» با موفقیت ارسال و در تاریخچه ثبت شد. سیستم در انتظار فایل جدید بعدی قرار گرفت.")
            else:
                self.append_log(f"⚠️ ارسال فایل «{latest['name']}» ناموفق بود و در تاریخچه ثبت نشد تا مجدداً تلاش شود.")
        finally:
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _safe_update_status_ui(self, status_text: str, status_color: str, countdown_text: str, countdown_color: str, last_sent_text: str, lic_text: str = "", lic_color: str = ""):
        """Thread-safe UI update callback executed on the main GUI thread."""
        try:
            self.lbl_service_status.configure(text=status_text, text_color=status_color)
            self.lbl_countdown.configure(text=countdown_text, text_color=countdown_color)
            self.lbl_last_sent.configure(text=last_sent_text)
            if lic_text and hasattr(self, "lbl_license_badge"):
                self.lbl_license_badge.configure(text=lic_text, text_color=lic_color)
        except Exception:
            pass

    def periodic_status_checker(self):
        while self.is_monitoring:
            try:
                running = is_worker_running()
                if running:
                    status_text = "وضعیت: 🟢 فعال (پایش پس‌زمینه)"
                    status_color = "#10B981"
                else:
                    status_text = "وضعیت: 🔴 متوقف شده"
                    status_color = "#EF4444"

                state = load_state()
                last_name = state.get("last_file_name")
                sent_at = state.get("last_sent_at")
                if last_name:
                    last_sent_text = f"آخرین ارسال: {last_name} ({sent_at})"
                else:
                    last_sent_text = "آخرین ارسال: هیچ فایلی ارسال نشده"

                # Check license
                lic_active, _, lic_info = is_license_active()
                if lic_active:
                    time_rem = lic_info.get("time_rem_str", "")
                    lic_text = f"🔒 اعتبار: {time_rem} وقت داری"
                    lic_color = "#10B981"
                else:
                    lic_text = "🔒 اعتبار: منقضی شده (نیاز به تمدید)"
                    lic_color = "#EF4444"

                # Check license expiration / danger alerts in Bale
                try:
                    from core.license_notifier import check_and_send_license_alerts
                    check_and_send_license_alerts()
                except Exception:
                    pass

                # Dynamic status display (read purely from config and disk to avoid cross-thread GUI reading)
                if not running:
                    countdown_text = "⏱ سرویس غیرفعال است"
                    countdown_color = "#94A3B8"
                else:
                    cfg = load_config()
                    raw_folder = cfg.get("folder_path", "").strip()
                    if raw_folder and os.path.isdir(raw_folder):
                        latest = get_latest_file(raw_folder)
                        if latest:
                            if is_file_already_sent(latest):
                                countdown_text = "🟢 منتظر فایل جدید (ارسال فقط با ورود فایل جدید)"
                                countdown_color = "#10B981"
                            else:
                                countdown_text = f"🔔 فایل جدید در صف ارسال: {latest['name']}"
                                countdown_color = "#D97706"
                        else:
                            countdown_text = "📂 پوشه خالی است (در انتظار فایل)"
                            countdown_color = "#64748B"
                    else:
                        countdown_text = "⚠️ پوشه نامعتبر است"
                        countdown_color = "#DC2626"

                # Safely dispatch UI updates to main thread
                if getattr(self, "is_monitoring", False):
                    try:
                        self.after(0, self._safe_update_status_ui, status_text, status_color, countdown_text, countdown_color, last_sent_text, lic_text, lic_color)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(1)

def main():
    if "--worker" in sys.argv:
        try:
            import service_worker
            service_worker.run_service_loop()
        except Exception as e:
            try:
                log_file = get_base_dir() / "service.log"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[FATAL WORKER ERROR] {datetime.now()}: {e}\n")
            except Exception:
                pass
        return
    app = BaleFileSenderApp()
    app.mainloop()

if __name__ == "__main__":
    main()
