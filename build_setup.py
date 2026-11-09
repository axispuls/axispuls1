import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

def build_single_file_setup():
    """
    Builds a single standalone executable (AxisPuls_Setup.exe) using PyInstaller.
    Includes all dependencies, assets, and core logic into ONE portable file.
    """
    print("==================================================================")
    print("       بسته‌بندی نرم‌افزار اکسیس پالس به صورت تک فایل ستاپ        ")
    print("       Building Standalone Single-File Setup (AxisPuls_Setup)      ")
    print("==================================================================")

    # Terminate any running instances to avoid Windows file locks on dist/AxisPuls_Setup.exe
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            pname = (p.info.get('name') or "").lower()
            if "axispuls" in pname:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass

    icon_path = BASE_DIR / "app_icon.ico"
    logo_path = BASE_DIR / "logo-original.png"
    core_dir = BASE_DIR / "core"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "AxisPuls_Setup",
        f"--icon={icon_path}",
        f"--add-data={core_dir};core",
        f"--add-data={logo_path};.",
        f"--add-data={icon_path};.",
        f"--add-data={BASE_DIR / 'service_worker.py'};.",
        "--collect-all", "customtkinter",
        "--collect-all", "certifi",
        "--collect-all", "requests_toolbelt",
        "--hidden-import", "requests_toolbelt",
        "--hidden-import", "core.hardware_info",
        "--hidden-import", "service_worker",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "urllib.request",
        "--hidden-import", "xml.etree.ElementTree",
        f"--paths={BASE_DIR}",
        str(BASE_DIR / "gui_app.py")
    ]

    print(f"Running command: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(BASE_DIR))

    dist_exe = BASE_DIR / "dist" / "AxisPuls_Setup.exe"
    if res.returncode == 0 and dist_exe.exists():
        size_mb = dist_exe.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 66)
        print(f"✅ ساخت فایل ستاپ با موفقیت انجام شد!")
        print(f"📁 مسیر فایل تک‌فایل نهایی: {dist_exe}")
        print(f"📦 حجم فایل: {size_mb:.2f} مگابایت")
        print("این تک‌فایل کاملاً مستقل بوده و برای هر کاربری قابل ارسال و اجراست.")
        print("=" * 66)
        return True
    else:
        print("\n❌ خطا در فرآیند ساخت فایل ستاپ!")
        return False

if __name__ == "__main__":
    success = build_single_file_setup()
    sys.exit(0 if success else 1)
