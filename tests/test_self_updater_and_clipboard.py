import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.self_updater import (
    validate_update_file,
    record_update_flag,
    check_and_notify_post_update,
    apply_update_and_restart,
    UPDATE_FLAG_FILE,
    UPDATE_DIR
)
from core.gui_clipboard_helper import (
    _get_target_entry_or_text,
    setup_global_clipboard_shortcuts
)

def test_validate_update_file_valid_pe(tmp_path):
    exe_file = tmp_path / "valid_setup.exe"
    # Valid Windows PE starts with b"MZ" and is >= 100 KB
    content = b"MZ" + b"\x00" * (120 * 1024)
    exe_file.write_bytes(content)

    ok, msg = validate_update_file(exe_file)
    assert ok is True
    assert "معتبر است" in msg

def test_validate_update_file_invalid_header(tmp_path):
    bad_file = tmp_path / "fake.exe"
    content = b"PK" + b"\x00" * (120 * 1024)  # ZIP header instead of PE
    bad_file.write_bytes(content)

    ok, msg = validate_update_file(bad_file)
    assert ok is False
    assert "ویندوز (EXE) نیست" in msg

def test_validate_update_file_too_small(tmp_path):
    small_file = tmp_path / "tiny.exe"
    small_file.write_bytes(b"MZ" + b"\x00" * 50)

    ok, msg = validate_update_file(small_file)
    assert ok is False
    assert "بسیار کم" in msg

def test_validate_update_file_nonexistent(tmp_path):
    missing_file = tmp_path / "does_not_exist.exe"
    ok, msg = validate_update_file(missing_file)
    assert ok is False
    assert "یافت نشد" in msg

def test_record_and_check_post_update(tmp_path):
    test_flag_file = tmp_path / "test_update_done.json"
    with patch("core.self_updater.UPDATE_FLAG_FILE", test_flag_file), \
         patch("core.self_updater.UPDATE_DIR", tmp_path), \
         patch("core.self_updater.send_message") as mock_send:

        # Record flag
        details = {
            "file_name": "AxisPuls_Setup.exe",
            "timestamp": "2026-11-09 12:00:00"
        }
        record_update_flag(details)
        assert test_flag_file.exists()

        # Check and notify
        check_and_notify_post_update("123:token")
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert "به‌روزرسانی با موفقیت انجام شد" in args[2]

        # Flag file should be deleted after notification
        assert not test_flag_file.exists()

def test_apply_update_and_restart(tmp_path):
    new_exe = tmp_path / "staged.exe"
    new_exe.write_bytes(b"MZ" + b"\x00" * (120 * 1024))

    with patch("core.self_updater.UPDATE_DIR", tmp_path), \
         patch("core.self_updater.get_current_executable_path", return_value=tmp_path / "target.exe"), \
         patch("subprocess.Popen") as mock_popen:
        ok, msg = apply_update_and_restart(new_exe)
        assert ok is True
        assert "اسکریپت جایگزینی" in msg
        mock_popen.assert_called_once()

def test_clipboard_helper_target_extraction():
    mock_entry = MagicMock()
    mock_inner = MagicMock()
    mock_entry._entry = mock_inner
    assert _get_target_entry_or_text(mock_entry) == mock_inner
