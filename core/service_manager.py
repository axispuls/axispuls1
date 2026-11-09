import os
import sys
import subprocess
import winreg
from pathlib import Path
import psutil
from .config_manager import get_base_dir
from .ssl_helper import get_permanent_ca_bundle

TASK_NAME = "BaleFolderAutoSender"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "BaleFolderAutoSender"

def get_worker_command() -> tuple[str, list[str]]:
    """
    Returns the executable and arguments to run the background worker.
    Uses pythonw.exe (no console window) in development or Worker.exe in frozen mode.
    """
    base_dir = get_base_dir()
    if getattr(sys, 'frozen', False):
        # In frozen mode, worker can be the same exe with --worker flag or a separate worker exe
        worker_exe = base_dir / "BaleWorker.exe"
        if worker_exe.exists():
            return str(worker_exe), []
        return str(Path(sys.executable)), ["--worker"]
    else:
        # Development mode: find pythonw.exe
        python_exe = sys.executable
        pythonw_exe = Path(python_exe).parent / "pythonw.exe"
        if not pythonw_exe.exists():
            pythonw_exe = Path(python_exe)
        worker_script = base_dir / "service_worker.py"
        return str(pythonw_exe), [str(worker_script)]

def is_worker_running() -> bool:
    """
    Checks if the background service worker process is currently running.
    """
    base_dir = get_base_dir()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            if "service_worker.py" in cmd_str or "baleworker.exe" in cmd_str:
                return True
            if "--worker" in cmdline:
                pname = (proc.info.get('name') or "").lower()
                if "axispuls" in pname or "baleworker" in pname:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False

def start_worker_process() -> bool:
    """
    Starts the worker process in background detached mode (no window).
    """
    if is_worker_running():
        return True

    exe, args = get_worker_command()
    cmd = [exe] + args

    # Windows flags to start fully detached without creating a console window
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    # Clean environment to prevent child process from inheriting stale parent PyInstaller paths
    ca_bundle = get_permanent_ca_bundle()
    child_env = os.environ.copy()
    for k in ["_MEIPASS", "_MEIPASS2"]:
        child_env.pop(k, None)
    if isinstance(ca_bundle, str) and os.path.exists(ca_bundle):
        child_env["REQUESTS_CA_BUNDLE"] = ca_bundle
        child_env["CURL_CA_BUNDLE"] = ca_bundle
        child_env["SSL_CERT_FILE"] = ca_bundle

    try:
        subprocess.Popen(
            cmd,
            cwd=str(get_base_dir()),
            env=child_env,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True
        )
        return True
    except Exception as e:
        print(f"Failed to start worker process: {e}")
        return False

def stop_worker_process() -> bool:
    """
    Stops all running instances of the worker process.
    """
    base_dir = get_base_dir()
    stopped = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            if "service_worker.py" in cmd_str or "baleworker.exe" in cmd_str or ("--worker" in cmd_str and str(base_dir).lower() in cmd_str):
                proc.terminate()
                stopped = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return stopped

def install_task_scheduler() -> tuple[bool, str]:
    """
    Creates a persistent Windows Scheduled Task that launches at user logon and startup.
    """
    exe, args = get_worker_command()
    if args:
        cmd_to_run = f'"{exe}" "{" ".join(args)}"'
    else:
        cmd_to_run = f'"{exe}"'

    base_dir = str(get_base_dir())

    # Create task with schtasks. Runs on logon with highest privileges
    command = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", cmd_to_run,
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/F"
    ]
    try:
        res = subprocess.run(command, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True, "وظیفه خودکار در Task Scheduler با موفقیت ثبت شد."
        else:
            return False, f"خطای ثبت در Task Scheduler: {res.stderr}"
    except Exception as e:
        return False, f"خطا در ارتباط با Task Scheduler: {str(e)}"

def remove_task_scheduler() -> tuple[bool, str]:
    """
    Deletes the Scheduled Task.
    """
    command = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    try:
        res = subprocess.run(command, capture_output=True, text=True, check=False)
        return True, "وظیفه Task Scheduler حذف شد."
    except Exception as e:
        return False, f"خطا در حذف وظیفه: {str(e)}"

def install_registry_autostart() -> tuple[bool, str]:
    """
    Sets registry key in HKCU Run to ensure auto-start on Windows login.
    """
    exe, args = get_worker_command()
    if args:
        val = f'"{exe}" "{" ".join(args)}"'
    else:
        val = f'"{exe}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, val)
        return True, "اجرای خودکار در رجیستری ویندوز ثبت شد."
    except Exception as e:
        return False, f"خطای ثبت در رجیستری: {str(e)}"

def remove_registry_autostart() -> tuple[bool, str]:
    """
    Removes registry key from HKCU Run.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_NAME)
        return True, "اجرای خودکار از رجیستری حذف شد."
    except FileNotFoundError:
        return True, "کلید در رجیستری وجود نداشت."
    except Exception as e:
        return False, f"خطا در حذف از رجیستری: {str(e)}"

def setup_full_autostart() -> tuple[bool, str]:
    """
    Installs both Task Scheduler and Registry auto-start for double resilience.
    """
    ok_reg, msg_reg = install_registry_autostart()
    ok_task, msg_task = install_task_scheduler()

    if ok_reg or ok_task:
        return True, "راه‌اندازی خودکار دائمی با موفقیت فعال شد."
    return False, f"خطا در فعال‌سازی: {msg_task} | {msg_reg}"

def remove_full_autostart() -> tuple[bool, str]:
    """
    Removes all auto-start triggers.
    """
    remove_registry_autostart()
    remove_task_scheduler()
    return True, "تمامی راه‌اندازی‌های خودکار غیرفعال شدند."
