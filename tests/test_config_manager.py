import pytest
from unittest.mock import patch
from core.config_manager import (
    load_config,
    save_config,
    get_active_user_ids,
    DEFAULT_CONFIG
)

@pytest.fixture(autouse=True)
def mock_config_file(tmp_path):
    mock_file = tmp_path / "mock_config.json"
    with patch("core.config_manager.CONFIG_FILE_PATH", mock_file):
        yield mock_file

def test_default_config_created():
    cfg = load_config()
    assert cfg["interval_minutes"] == 15
    assert cfg["autostart_enabled"] is True
    assert len(cfg["user_ids"]) == 3

def test_save_and_reload():
    test_data = {
        "folder_path": "C:\\TargetFiles",
        "bot_token": "123456:ABCdefGHI",
        "user_ids": ["111222", "333444", ""],
        "interval_minutes": 10,
        "autostart_enabled": False
    }
    assert save_config(test_data) is True
    loaded = load_config()
    assert loaded["folder_path"] == "C:\\TargetFiles"
    assert loaded["bot_token"] == "123456:ABCdefGHI"
    assert loaded["interval_minutes"] == 10
    assert loaded["autostart_enabled"] is False

def test_get_active_user_ids():
    cfg = {
        "user_ids": ["1001", "  1002  ", "invalid_id", "1001", ""]
    }
    active = get_active_user_ids(cfg)
    # Must remove duplicates, trim spaces, and discard non-numeric
    assert active == ["1001", "1002"]
