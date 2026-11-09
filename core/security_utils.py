import os
import re
import time
from pathlib import Path
from typing import Optional

# Windows reserved device names that must never be opened or traversed
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

def mask_token(token: str) -> str:
    """
    Masks the bot token to prevent credential exposure in logs and errors.
    Example: '123456789:ABCdefGHIjk' -> '123456***...***jk'
    """
    token = str(token).strip()
    if not token:
        return "<EMPTY_TOKEN>"
    if len(token) <= 8:
        return "***"
    prefix = token[:6]
    suffix = token[-3:]
    return f"{prefix}***{suffix}"

def sanitize_user_id(user_id_input: any) -> Optional[str]:
    """
    Validates and cleans user ID. Must be non-empty and strictly numeric.
    Returns cleaned numeric string, or None if invalid.
    """
    if user_id_input is None:
        return None
    s = str(user_id_input).strip()
    if not s:
        return None
    # Allow optional leading '-' for channel/supergroup IDs, but strictly digits thereafter
    if re.match(r'^-?\d+$', s):
        return s
    return None

def validate_safe_folder(folder_path_input: str) -> tuple[bool, str, Optional[Path]]:
    """
    Performs security and safety audit on folder path:
    - Path must not be empty
    - Must not use reserved Windows names
    - Resolves absolute path
    - Must exist and be a directory
    """
    if not folder_path_input or not str(folder_path_input).strip():
        return False, "مسیر پوشه خالی است.", None

    try:
        path = Path(folder_path_input).resolve()
        
        # Check against Windows reserved device names
        for part in path.parts:
            stem = part.split(".")[0].upper()
            if stem in WINDOWS_RESERVED_NAMES:
                return False, f"مسیر شامل نام‌های رزرو شده سیستمی است: {part}", None

        if not path.exists():
            return False, f"پوشه مورد نظر در سیستم یافت نشد: {path}", None

        if not path.is_dir():
            return False, f"مسیر داده شده یک پوشه نیست: {path}", None

        return True, "مسیر معتبر است.", path
    except Exception as e:
        return False, f"خطا در اعتبارسنجی مسیر: {str(e)}", None

def atomic_write_json(file_path: Path, content: str) -> bool:
    """
    Writes data to a unique temporary file first, then atomically replaces the target file.
    Prevents file corruption if the process terminates mid-write, and avoids collisions.
    """
    temp_path = file_path.with_name(f"{file_path.stem}_{os.getpid()}_{time.time_ns()}.tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Atomic replace on Windows
        os.replace(temp_path, file_path)
        return True
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return False
