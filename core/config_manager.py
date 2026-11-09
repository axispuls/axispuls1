import os
import json
import sys
from pathlib import Path
from .security_utils import sanitize_user_id, atomic_write_json

def get_base_dir() -> Path:
    """Returns the base directory of the script or compiled exe."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.parent.resolve()

CONFIG_FILE_PATH = get_base_dir() / "config.json"

DEFAULT_CONFIG = {
    "folder_path": "",
    "bot_token": "",
    "bot_username": "",
    "user_ids": ["", "", ""],
    "interval_minutes": 15,
    "autostart_enabled": True,
    "compression_mode": "deflate_max",
    "auto_compress_all": False
}

def load_config() -> dict:
    """Load configuration from config.json or return default config."""
    if not CONFIG_FILE_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            user_ids = config.get("user_ids", [])
            while len(user_ids) < 3:
                user_ids.append("")
            config["user_ids"] = user_ids[:3]
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config_data: dict) -> bool:
    """Save configuration atomically to config.json."""
    try:
        content = json.dumps(config_data, ensure_ascii=False, indent=4)
        return atomic_write_json(CONFIG_FILE_PATH, content)
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_active_user_ids(config_data: dict) -> list[str]:
    """Returns valid non-empty sanitized numeric user IDs."""
    raw_ids = config_data.get("user_ids", [])
    active = []
    for uid in raw_ids:
        cleaned = sanitize_user_id(uid)
        if cleaned and cleaned not in active:
            active.append(cleaned)
    return active
