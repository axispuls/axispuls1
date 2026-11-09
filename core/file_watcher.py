import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

IGNORE_EXTENSIONS = {".tmp", ".part", ".crdownload", ".lock", ".swp"}

def resolve_shortcut_target(file_path: str) -> Optional[str]:
    """
    If file is a Windows .lnk shortcut, resolves it to the actual target file path.
    Returns target path if it exists and is a regular file, otherwise returns None.
    """
    if not file_path.lower().endswith(".lnk"):
        return file_path
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(file_path)
        target = shortcut.Targetpath
        if target and os.path.isfile(target):
            return os.path.abspath(target)
    except Exception:
        pass
    return None

def format_file_size(size_in_bytes: int) -> str:
    """Formats bytes into human readable format (KB, MB, GB)."""
    for unit in ['بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} ترابایت"

def is_file_ready(file_path: str) -> bool:
    """
    Checks if a file has finished being written by checking its size
    over a short interval and attempting to open it for reading.
    """
    try:
        if not os.path.isfile(file_path):
            return False
        
        # Check if file can be opened
        with open(file_path, "rb") as f:
            f.read(1)
        
        # Check size stability
        size1 = os.path.getsize(file_path)
        time.sleep(0.3)
        size2 = os.path.getsize(file_path)
        return size1 == size2
    except (PermissionError, IOError, OSError):
        return False

def get_latest_file(folder_path: str) -> Optional[Dict[str, Any]]:
    """
    Finds and returns details of the latest modified file in the folder.
    Returns None if the directory doesn't exist or has no valid files.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return None

    valid_files = []
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    
                    # Skip hidden and temporary files
                    name = entry.name
                    if name.startswith(".") or name.startswith("~"):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    if ext in IGNORE_EXTENSIONS:
                        continue

                    # Handle Windows shortcuts (.lnk)
                    resolved_path = os.path.abspath(entry.path)
                    resolved_name = name
                    if ext == ".lnk":
                        target = resolve_shortcut_target(entry.path)
                        if not target:
                            # Skip broken shortcuts
                            continue
                        resolved_path = target
                        resolved_name = os.path.basename(target)
                        stat = os.stat(target)
                        # Use the shortcut's own arrival time in this folder as effective arrival time
                        shortcut_stat = entry.stat()
                        effective_time = max(shortcut_stat.st_mtime, getattr(shortcut_stat, "st_ctime", shortcut_stat.st_mtime))
                    else:
                        stat = entry.stat()
                        effective_time = max(stat.st_mtime, getattr(stat, "st_ctime", stat.st_mtime))

                    valid_files.append({
                        "name": resolved_name,
                        "path": resolved_path,
                        "mtime": effective_time,
                        "effective_time": effective_time,
                        "size": stat.st_size
                    })
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except Exception as e:
        print(f"Error accessing directory {folder_path}: {e}")
        return None

    if not valid_files:
        return None

    # Sort files by effective time descending (newest arrival / modification first)
    valid_files.sort(key=lambda x: x["effective_time"], reverse=True)

    # Find the first one that is ready and not locked
    for file_info in valid_files:
        if is_file_ready(file_info["path"]):
            try:
                dt = datetime.fromtimestamp(file_info["mtime"])
                file_info["formatted_mtime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                file_info["formatted_mtime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_info["readable_size"] = format_file_size(file_info["size"])
            return file_info

    return None
