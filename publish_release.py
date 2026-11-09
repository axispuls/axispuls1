"""
Axis Puls - Automated GitHub Release & Deployment CLI
Usage:
    python publish_release.py [version] [notes] [--skip-build]
Example:
    python publish_release.py 1.0.1 "به‌روزرسانی هسته و رفع اشکالات"
"""

import sys
import subprocess
from pathlib import Path

from core.version import get_current_version
from core.github_updater import publish_new_release, get_publisher_config
from core.config_manager import get_base_dir

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    skip_build = "--skip-build" in flags

    version = args[0] if len(args) > 0 else "1.0.1"
    notes = args[1] if len(args) > 1 else "به‌روزرسانی خودکار و بهبود پایداری سیستم."

    base_dir = get_base_dir()
    setup_exe = base_dir / "dist" / "AxisPuls_Setup.exe"

    if not skip_build:
        print("🔨 در حال کامپایل و ساخت فایل ستاپ جدید (build_setup.py)...")
        res = subprocess.run([sys.executable, "build_setup.py"], cwd=str(base_dir))
        if res.returncode != 0:
            print("❌ خطا در کامپایل ستاپ.")
            sys.exit(1)

    if not setup_exe.exists():
        print(f"❌ فایل ستاپ در مسیر {setup_exe} یافت نشد.")
        sys.exit(1)

    cfg = get_publisher_config()
    token = cfg.get("github_token")
    owner = cfg.get("repo_owner", "axispuls")
    repo = cfg.get("repo_name", "axispuls1")

    print(f"🚀 در حال انتشار نسخه {version} در مخزن {owner}/{repo}...")
    ok, msg = publish_new_release(
        version=version,
        release_notes=notes,
        setup_exe_path=setup_exe,
        token=token,
        repo_owner=owner,
        repo_name=repo,
        log_callback=print
    )

    if ok:
        print("\n🎉 انتشار با موفقیت انجام شد!")
        print(msg)
    else:
        print(f"\n❌ شکست در انتشار: {msg}")
        sys.exit(1)

if __name__ == "__main__":
    main()
