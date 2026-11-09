import os
import time
import pytest
from pathlib import Path
from core.file_watcher import (
    get_latest_file,
    format_file_size,
    is_file_ready
)

def test_empty_folder(tmp_path):
    """Empty folder must return None."""
    assert get_latest_file(str(tmp_path)) is None

def test_nonexistent_folder():
    """Nonexistent folder must return None without raising uncaught exceptions."""
    assert get_latest_file("Z:\\Invalid\\NonExistentPath_12345") is None

def test_strictly_latest_file_selected(tmp_path):
    """
    When multiple files exist in the folder, ONLY the single latest modified file
    must be returned.
    """
    f1 = tmp_path / "oldest_file.txt"
    f1.write_text("file 1")
    time.sleep(1.05)

    f2 = tmp_path / "middle_file.pdf"
    f2.write_text("file 2")
    time.sleep(1.05)

    f3 = tmp_path / "newest_file.zip"
    f3.write_text("file 3 is the newest")

    latest = get_latest_file(str(tmp_path))
    assert latest is not None
    assert latest["name"] == "newest_file.zip"
    assert latest["path"] == str(f3.resolve())
    assert latest["size"] == len("file 3 is the newest")

def test_temporary_and_hidden_files_ignored(tmp_path):
    """
    Temporary download files (.tmp, .part, .crdownload) and hidden files
    must be completely ignored, even if their modification date is newer.
    """
    valid_file = tmp_path / "document.docx"
    valid_file.write_text("valid document content")
    time.sleep(1.05)

    # Newer temporary files
    (tmp_path / "download.crdownload").write_text("downloading...")
    (tmp_path / "temp_cache.tmp").write_text("temporary...")
    (tmp_path / "video.part").write_text("partial...")
    (tmp_path / "~$word_lock.docx").write_text("lock file...")
    (tmp_path / ".hidden_file").write_text("hidden...")

    latest = get_latest_file(str(tmp_path))
    assert latest is not None
    assert latest["name"] == "document.docx"

def test_format_file_size():
    """Human readable file size formatting."""
    assert "بایت" in format_file_size(500)
    assert "کیلوبایت" in format_file_size(2048)
    assert "مگابایت" in format_file_size(5 * 1024 * 1024)
    assert "گیگابایت" in format_file_size(3 * 1024 * 1024 * 1024)

def test_is_file_ready(tmp_path):
    """Checks if a file is readable and ready."""
    sample = tmp_path / "ready.txt"
    sample.write_text("ready content")
    assert is_file_ready(str(sample)) is True
    assert is_file_ready(str(tmp_path / "non_existing.txt")) is False

def test_broken_shortcut_ignored(tmp_path):
    """A broken .lnk shortcut that points to nothing must be ignored."""
    broken_lnk = tmp_path / "broken.lnk"
    broken_lnk.write_bytes(b"invalid shortcut binary data")
    time.sleep(1.05)
    real_file = tmp_path / "real.txt"
    real_file.write_text("real content")
    
    latest = get_latest_file(str(tmp_path))
    assert latest is not None
    assert latest["name"] == "real.txt"
