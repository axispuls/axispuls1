import pytest
from unittest.mock import patch
from core.state_manager import (
    load_state,
    save_state,
    is_file_already_sent,
    record_sent_file
)

@pytest.fixture(autouse=True)
def mock_state_file(tmp_path):
    mock_file = tmp_path / "mock_state.json"
    with patch("core.state_manager.STATE_FILE_PATH", mock_file):
        yield mock_file

def test_initial_state_empty():
    state = load_state()
    assert state["last_file_name"] == ""
    assert state["last_file_mtime"] == 0.0
    assert state["last_file_size"] == 0

def test_record_and_check_sent_file():
    file_info = {
        "name": "report_2026.pdf",
        "path": "C:\\data\\report_2026.pdf",
        "mtime": 172948200.0,
        "size": 1048576
    }

    # Before recording, must NOT be marked as sent
    assert is_file_already_sent(file_info) is False

    # Record the file
    record_sent_file(file_info)

    # Now it MUST be marked as already sent
    assert is_file_already_sent(file_info) is True

    # Same file name but different size -> Considered NEW / MODIFIED
    modified_size_file = file_info.copy()
    modified_size_file["size"] = 2048000
    assert is_file_already_sent(modified_size_file) is False

    # Same file name but different mtime -> Considered NEW / MODIFIED
    modified_mtime_file = file_info.copy()
    modified_mtime_file["mtime"] = 172950000.0
    assert is_file_already_sent(modified_mtime_file) is False

    # Completely different file -> Considered NEW
    different_file = {
        "name": "different_doc.xlsx",
        "path": "C:\\data\\different_doc.xlsx",
        "mtime": 172948250.0,
        "size": 512000
    }
    assert is_file_already_sent(different_file) is False

def test_history_limit():
    for i in range(60):
        record_sent_file({
            "name": f"file_{i}.txt",
            "path": f"C:\\file_{i}.txt",
            "mtime": float(i),
            "size": i * 10
        })

    state = load_state()
    # History must cap at 50 to prevent unbounded memory/file growth
    assert len(state["history"]) == 50
    assert state["last_file_name"] == "file_59.txt"

def test_baseline_folder_contents_ignores_existing_files(tmp_path):
    from core.state_manager import is_folder_baselined, baseline_folder_contents
    folder = tmp_path / "existing_backup_dir"
    folder.mkdir()

    # Pre-existing file
    old_file = folder / "old_backup.bak"
    old_file.write_bytes(b"Old backup data from yesterday")

    assert is_folder_baselined(str(folder)) is False

    # Baseline the folder
    base_file = baseline_folder_contents(str(folder))
    assert base_file is not None
    assert base_file["name"] == "old_backup.bak"

    # Now folder is marked as baselined
    assert is_folder_baselined(str(folder)) is True

    # Pre-existing file MUST now be considered already sent/known!
    from core.file_watcher import get_latest_file
    cur_latest = get_latest_file(str(folder))
    assert is_file_already_sent(cur_latest) is True

    # When a truly NEW file is added:
    import time
    time.sleep(1.05)
    new_file = folder / "new_backup.bak"
    new_file.write_bytes(b"Brand new backup data created today")

    new_latest = get_latest_file(str(folder))
    assert new_latest["name"] == "new_backup.bak"
    # New file MUST NOT be considered sent!
    assert is_file_already_sent(new_latest) is False

