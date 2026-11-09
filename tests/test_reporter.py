import os
import time
import pytest
from pathlib import Path
from core.reporter import format_remaining_time, generate_5min_status_report
from core.state_manager import record_sent_file

@pytest.fixture
def test_folder_env(tmp_path):
    target_dir = tmp_path / "reporter_watch_dir"
    target_dir.mkdir()
    state_file = tmp_path / "mock_state.json"
    from unittest.mock import patch
    with patch("core.state_manager.STATE_FILE_PATH", state_file):
        yield target_dir

def test_format_remaining_time():
    assert "هم‌اکنون" in format_remaining_time(0)
    assert "هم‌اکنون" in format_remaining_time(-10)
    assert format_remaining_time(120) == "2 دقیقه"
    assert format_remaining_time(150) == "2 دقیقه و 30 ثانیه"
    assert format_remaining_time(45) == "45 ثانیه"

def test_report_invalid_folder():
    report = generate_5min_status_report("Z:\\invalid_folder_123", 2, time.time() + 300, 15)
    assert report["is_valid"] is False
    assert report["has_new_file"] is False
    assert "یافت نشد" in report["report_text"] or "معتبر نیست" in report["report_text"]

def test_report_empty_folder(test_folder_env):
    target_dir = test_folder_env
    report = generate_5min_status_report(str(target_dir), 2, time.time() + 300, 15)
    assert report["is_valid"] is True
    assert report["has_new_file"] is False
    assert "هیچ فایل معتبری" in report["report_text"]

def test_report_new_file_under_20mb(test_folder_env):
    target_dir = test_folder_env
    doc = target_dir / "daily_stats.csv"
    doc.write_text("col1,col2\n10,20\n")

    next_epoch = time.time() + 600  # 10 minutes remaining
    report = generate_5min_status_report(str(target_dir), 3, next_epoch, 15)

    assert report["is_valid"] is True
    assert report["has_new_file"] is True
    assert report["latest_file"]["name"] == "daily_stats.csv"
    assert "daily_stats.csv" in report["report_text"]
    assert "بله، فایل جدید است" in report["report_text"]
    assert "ارسال مستقیم" in report["report_text"]
    assert "دقیقه" in report["report_text"]
    assert "3 کاربر" in report["report_text"]

def test_report_already_sent_file(test_folder_env):
    target_dir = test_folder_env
    doc = target_dir / "already_sent_file.pdf"
    doc.write_bytes(b"%PDF content")

    from core.file_watcher import get_latest_file
    latest = get_latest_file(str(target_dir))
    record_sent_file(latest)

    next_epoch = time.time() + 300  # 5 minutes remaining
    report = generate_5min_status_report(str(target_dir), 2, next_epoch, 15)

    assert report["is_valid"] is True
    assert report["has_new_file"] is False
    assert "خیر، فایل جدیدی نیست" in report["report_text"]
    assert "دقیقه" in report["report_text"]

def test_report_over_20mb_file(test_folder_env):
    target_dir = test_folder_env
    large_file = target_dir / "large_video.mp4"
    large_file.write_bytes(b"0" * (21 * 1024 * 1024))  # 21 MB

    report = generate_5min_status_report(str(target_dir), 1, time.time() + 900, 15)
    assert report["has_new_file"] is True
    assert "پارت‌های زیپ" in report["report_text"]
