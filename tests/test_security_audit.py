import os
import pytest
from pathlib import Path
from core.security_utils import (
    mask_token,
    sanitize_user_id,
    validate_safe_folder,
    atomic_write_json
)

def test_token_masking():
    """Bot token must never be printed in plain text."""
    token = "123456789:ABCdefGHIjklMNopQRst"
    masked = mask_token(token)
    assert token not in masked
    assert masked.startswith("123456")
    assert masked.endswith("Rst")
    assert "***" in masked

    # Edge cases
    assert mask_token("") == "<EMPTY_TOKEN>"
    assert mask_token("123") == "***"

def test_user_id_sanitization():
    """User ID must be strictly numeric to prevent injection or malformed requests."""
    assert sanitize_user_id("123456789") == "123456789"
    assert sanitize_user_id("  987654321  ") == "987654321"
    assert sanitize_user_id("-100123456789") == "-100123456789"  # Channel/Supergroup
    assert sanitize_user_id(12345) == "12345"

    # Malicious or invalid inputs must return None
    assert sanitize_user_id("1234; DROP TABLE users;") is None
    assert sanitize_user_id("<script>alert(1)</script>") is None
    assert sanitize_user_id("abc12345") is None
    assert sanitize_user_id("123.45") is None
    assert sanitize_user_id("") is None
    assert sanitize_user_id(None) is None

def test_safe_folder_validation(tmp_path):
    """Folder validation must prevent path traversal to invalid directories or reserved device names."""
    valid_dir = tmp_path / "my_valid_folder"
    valid_dir.mkdir()

    # Valid folder
    ok, msg, p = validate_safe_folder(str(valid_dir))
    assert ok is True
    assert p == valid_dir.resolve()

    # Nonexistent folder
    ok, msg, p = validate_safe_folder(str(tmp_path / "non_existing_dir_xyz"))
    assert ok is False
    assert "یافت نشد" in msg

    # File instead of directory
    a_file = tmp_path / "not_a_dir.txt"
    a_file.write_text("hello")
    ok, msg, p = validate_safe_folder(str(a_file))
    assert ok is False
    assert "پوشه نیست" in msg

    # Empty path
    ok, msg, p = validate_safe_folder("")
    assert ok is False

    # Windows reserved device names
    for reserved in ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]:
        ok, msg, p = validate_safe_folder(f"C:\\{reserved}\\test")
        assert ok is False
        assert "رزرو شده" in msg

def test_atomic_write_json(tmp_path):
    """Atomic write must safely update file content without partial writes."""
    target_file = tmp_path / "test_atomic.json"
    content = '{"status": "ok", "value": 42}'

    assert atomic_write_json(target_file, content) is True
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == content

    # Overwrite with new content
    new_content = '{"status": "updated", "value": 99}'
    assert atomic_write_json(target_file, new_content) is True
    assert target_file.read_text(encoding="utf-8") == new_content

    # Ensure no lingering .tmp file
    assert not target_file.with_suffix(".tmp").exists()
