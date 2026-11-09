import os
import json
import time
from pathlib import Path
from datetime import datetime
from .config_manager import get_base_dir
from .security_utils import atomic_write_json

STATE_FILE_PATH = get_base_dir() / "state.json"

DEFAULT_STATE = {
    "last_file_name": "",
    "last_file_path": "",
    "last_file_mtime": 0.0,
    "last_file_size": 0,
    "last_sent_at": "",
    "next_send_epoch": 0.0,
    "next_send_time_str": "",
    "history": [],
    "baselined_folders": {}
}

def load_state() -> dict:
    """Loads state from state.json."""
    if not STATE_FILE_PATH.exists():
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()
    try:
        with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            state = DEFAULT_STATE.copy()
            state.update(data)
            return state
    except Exception as e:
        print(f"Error loading state: {e}")
        return DEFAULT_STATE.copy()

def save_state(state_data: dict) -> bool:
    """Saves state atomically to state.json."""
    try:
        content = json.dumps(state_data, ensure_ascii=False, indent=4)
        return atomic_write_json(STATE_FILE_PATH, content)
    except Exception as e:
        print(f"Error saving state: {e}")
        return False

def is_file_already_sent(file_info: dict) -> bool:
    """
    Checks if the given file has already been sent based on state.json.
    Compares filename, mtime (within 1s margin), and size.
    """
    state = load_state()
    # Check directly with the last sent file
    if state.get("last_file_name") == file_info.get("name"):
        mtime_diff = abs(state.get("last_file_mtime", 0.0) - file_info.get("mtime", 0.0))
        size_match = state.get("last_file_size", 0) == file_info.get("size", 0)
        if mtime_diff < 1.0 and size_match:
            return True

    # Also check against recent history
    for entry in state.get("history", []):
        if entry.get("name") == file_info.get("name"):
            mtime_diff = abs(entry.get("mtime", 0.0) - file_info.get("mtime", 0.0))
            if mtime_diff < 1.0 and entry.get("size", 0) == file_info.get("size", 0):
                return True
    return False

def record_sent_file(file_info: dict) -> None:
    """
    Records the sent file into state.json.
    """
    state = load_state()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "name": file_info.get("name", ""),
        "path": file_info.get("path", ""),
        "mtime": file_info.get("mtime", 0.0),
        "size": file_info.get("size", 0),
        "sent_at": now_str
    }
    state["last_file_name"] = entry["name"]
    state["last_file_path"] = entry["path"]
    state["last_file_mtime"] = entry["mtime"]
    state["last_file_size"] = entry["size"]
    state["last_sent_at"] = now_str

    history = state.get("history", [])
    history.insert(0, entry)
    state["history"] = history[:50]  # keep last 50 entries
    save_state(state)

def get_last_upload_speed() -> float:
    """
    Returns last measured upload speed in bytes/sec from state.json.
    Defaults to 0.0 if not yet measured.
    """
    state = load_state()
    return float(state.get("last_upload_speed_bps", 0.0))

def set_last_upload_speed(speed_bps: float) -> None:
    """
    Saves the real-time measured upload speed in bytes/sec to state.json.
    """
    if speed_bps and speed_bps > 0:
        state = load_state()
        state["last_upload_speed_bps"] = round(float(speed_bps), 2)
        save_state(state)

def set_next_send_epoch(epoch: float) -> None:
    """Updates next send epoch and readable time in state safely."""
    state = load_state()
    state["next_send_epoch"] = epoch
    if epoch > 0:
        try:
            dt = datetime.fromtimestamp(epoch)
            state["next_send_time_str"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            state["next_send_time_str"] = ""
    else:
        state["next_send_time_str"] = ""
    save_state(state)

def get_next_send_epoch() -> float:
    """Retrieves next send epoch from state."""
    state = load_state()
    return float(state.get("next_send_epoch", 0.0))

def is_folder_baselined(folder_path: str) -> bool:
    """Checks if the folder has already been baselined on initial setup."""
    if not folder_path:
        return False
    state = load_state()
    try:
        norm = str(Path(folder_path).resolve()).lower()
    except Exception:
        norm = str(folder_path).strip().lower()
    return norm in state.get("baselined_folders", {})

def baseline_folder_contents(folder_path: str) -> dict:
    """
    Baselines all existing files in the given folder when configured for the first time.
    Marks pre-existing files as already known/sent so existing files are NOT sent.
    The system will only send NEW files created/modified after this baseline.
    Returns the latest pre-existing file info if any existed, or None if folder was empty.
    """
    if not folder_path:
        return None

    from .file_watcher import get_latest_file
    state = load_state()
    try:
        norm = str(Path(folder_path).resolve()).lower()
    except Exception:
        norm = str(folder_path).strip().lower()

    latest = get_latest_file(folder_path)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    baselined_dict = state.get("baselined_folders", {})
    baselined_dict[norm] = {
        "baselined_at": now_str,
        "latest_file_name": latest["name"] if latest else None,
        "latest_file_mtime": latest["mtime"] if latest else 0.0
    }
    state["baselined_folders"] = baselined_dict

    if latest:
        state["last_file_name"] = latest["name"]
        state["last_file_path"] = latest["path"]
        state["last_file_mtime"] = latest["mtime"]
        state["last_file_size"] = latest["size"]
        state["last_sent_at"] = f"baseline_{now_str}"

        history = state.get("history", [])
        entry = {
            "name": latest["name"],
            "path": latest["path"],
            "mtime": latest["mtime"],
            "size": latest["size"],
            "sent_at": f"baseline_{now_str}"
        }
        if not any(h.get("name") == latest["name"] and abs(h.get("mtime", 0) - latest["mtime"]) < 1.0 for h in history):
            history.insert(0, entry)
        state["history"] = history[:50]

    save_state(state)
    return latest
