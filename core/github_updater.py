import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, Callable

from .config_manager import get_base_dir
from .version import get_current_version, is_newer_version
from .self_updater import validate_update_file, apply_update_and_restart

DEFAULT_REPO_OWNER = "axispuls"
DEFAULT_REPO_NAME = "axispuls1"
SETUP_EXE_NAME = "AxisPuls_Setup.exe"

EMBEDDED_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def get_publisher_config() -> Dict[str, Any]:
    """Reads local developer configuration for publishing releases."""
    cfg_paths = [
        get_base_dir() / "github_publisher_config.json",
        get_base_dir().parent / "github_publisher_config.json"
    ]
    for p in cfg_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {
        "repo_owner": DEFAULT_REPO_OWNER,
        "repo_name": DEFAULT_REPO_NAME,
        "github_token": EMBEDDED_GITHUB_TOKEN
    }

def check_for_github_update(
    repo_owner: str = DEFAULT_REPO_OWNER,
    repo_name: str = DEFAULT_REPO_NAME,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks GitHub Releases API for the latest published release.
    Returns dictionary with release details and whether an update is available.
    """
    cur_ver = get_current_version()
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"

    headers = {
        "User-Agent": "AxisPuls-Updater",
        "Accept": "application/vnd.github.v3+json"
    }

    # If no token passed, check local config
    if not token:
        token = get_publisher_config().get("github_token")

    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "has_update": False, "error": "هنوز هیچ نسخه‌ای در گیت‌هاب منتشر نشده است."}
        return {"ok": False, "has_update": False, "error": f"خطای ارتباط با گیت‌هاب (کد {e.code})"}
    except Exception as e:
        return {"ok": False, "has_update": False, "error": f"خطا در بررسی به‌روزرسانی: {e}"}

    latest_tag = data.get("tag_name", "1.0.0")
    has_update = is_newer_version(latest_tag, cur_ver)
    body = data.get("body", "")

    # Locate setup binary asset
    assets = data.get("assets", [])
    setup_asset = None
    for a in assets:
        if a.get("name", "").lower().endswith(".exe"):
            setup_asset = a
            break

    download_url = setup_asset.get("browser_download_url") if setup_asset else None
    size_bytes = setup_asset.get("size", 0) if setup_asset else 0
    size_mb = round(size_bytes / (1024 * 1024), 2)

    return {
        "ok": True,
        "has_update": has_update,
        "current_version": cur_ver,
        "latest_version": latest_tag,
        "release_name": data.get("name", latest_tag),
        "notes": body,
        "asset_name": setup_asset.get("name") if setup_asset else None,
        "download_url": download_url,
        "asset_size_mb": size_mb,
        "published_at": data.get("published_at")
    }

def download_github_release_asset(
    download_url: str,
    target_path: Path,
    token: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, float], None]] = None
) -> Tuple[bool, str]:
    """
    Downloads the setup binary asset from GitHub.
    Handles redirects and writes to target_path safely.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target_path.with_suffix(".tmp_download")

    headers = {
        "User-Agent": "AxisPuls-Updater",
        "Accept": "application/octet-stream"
    }

    if not token:
        token = get_publisher_config().get("github_token")

    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(download_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(temp_target, "wb") as out_file:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    percent = round((downloaded / total_size) * 100, 1)
                    progress_callback(downloaded, total_size, percent)

        # Atomic rename after full download
        if temp_target.exists():
            temp_target.replace(target_path)

        # Validate executable
        valid, msg = validate_update_file(target_path)
        if not valid:
            target_path.unlink(missing_ok=True)
            return False, f"فایل دانلود شده نامعتبر است: {msg}"

        return True, "فایل به‌روزرسانی با موفقیت دانلود و اعتبارسنجی گردید."
    except Exception as e:
        if temp_target.exists():
            temp_target.unlink(missing_ok=True)
        return False, f"خطا در دانلود فایل به‌روزرسانی: {e}"

def publish_new_release(
    version: str,
    release_notes: str,
    setup_exe_path: Path,
    token: Optional[str] = None,
    repo_owner: str = DEFAULT_REPO_OWNER,
    repo_name: str = DEFAULT_REPO_NAME,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Creates a new GitHub Release and uploads the setup executable as an asset.
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not token:
        token = get_publisher_config().get("github_token")

    if not token:
        return False, "توکن گیت‌هاب (Personal Access Token) تنظیم نشده است."

    if not setup_exe_path.exists():
        return False, f"فایل ستاپ در مسیر {setup_exe_path} یافت نشد."

    valid, vmsg = validate_update_file(setup_exe_path)
    if not valid:
        return False, f"فایل ستاپ نامعتبر است: {vmsg}"

    clean_tag = version.strip()
    if not clean_tag.startswith("v"):
        clean_tag = f"v{clean_tag}"

    log(f"🚀 در حال ایجاد انتشار (Release) نسخه {clean_tag} در گیت‌هاب...")

    # 1. Create Release via GitHub API
    create_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases"
    payload = {
        "tag_name": clean_tag,
        "name": f"اکسیس پالس {clean_tag}",
        "body": release_notes,
        "draft": False,
        "prerelease": False
    }

    req = urllib.request.Request(
        create_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {token}",
            "User-Agent": "AxisPuls-Publisher",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rel_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return False, f"خطا در ایجاد Release (کد {e.code}): {err_body}"
    except Exception as e:
        return False, f"خطای ناشناخته در ایجاد Release: {e}"

    upload_url_template = rel_data.get("upload_url", "")
    # Format of upload_url is: https://uploads.github.com/repos/.../releases/{id}/assets{?name,label}
    upload_url = upload_url_template.split("{")[0] + f"?name={setup_exe_path.name}"

    file_size = setup_exe_path.stat().st_size
    size_mb = round(file_size / (1024 * 1024), 2)
    log(f"📦 در حال آپلود فایل ستاپ ({setup_exe_path.name} | {size_mb} MB) به گیت‌هاب...")

    try:
        with open(setup_exe_path, "rb") as f:
            file_data = f.read()

        up_req = urllib.request.Request(
            upload_url,
            data=file_data,
            headers={
                "Authorization": f"token {token}",
                "User-Agent": "AxisPuls-Publisher",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file_size)
            },
            method="POST"
        )

        with urllib.request.urlopen(up_req, timeout=180) as up_resp:
            asset_data = json.loads(up_resp.read().decode("utf-8"))
            asset_download_url = asset_data.get("browser_download_url", "")

        log("✅ فایل ستاپ با موفقیت در گیت‌هاب آپلود شد.")
        return True, f"نسخه {clean_tag} با موفقیت در گیت‌هاب منتشر شد!\nلینک دانلود: {asset_download_url}"
    except Exception as e:
        return False, f"خطا در آپلود فایل ستاپ به Release: {e}"
