import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import service_worker
from core.state_manager import load_state, is_file_already_sent

@pytest.fixture
def mock_integration_environment(tmp_path):
    monitored_dir = tmp_path / "monitored_folder"
    monitored_dir.mkdir()

    cfg_file = tmp_path / "config.json"
    state_file = tmp_path / "state.json"
    reg_users_file = tmp_path / "registered_users.json"
    temp_dir = tmp_path / "temp_parts"

    with patch("core.config_manager.CONFIG_FILE_PATH", cfg_file), \
         patch("core.state_manager.STATE_FILE_PATH", state_file), \
         patch("core.bale_listener.REGISTERED_USERS_FILE", reg_users_file), \
         patch("core.license_manager.is_license_active", return_value=(True, "Active", {"remaining_days": 365})), \
         patch("service_worker.TEMP_DIR", temp_dir), \
         patch("service_worker.broadcast_message", return_value={}), \
         patch("service_worker.send_message_async"), \
         patch("service_worker.broadcast_message_async"):

        # Setup initial configuration
        from core.config_manager import save_config
        save_config({
            "folder_path": str(monitored_dir),
            "bot_token": "123456:valid_mock_token",
            "user_ids": ["1001", "1002", ""],
            "interval_minutes": 15,
            "autostart_enabled": True
        })

        yield monitored_dir, temp_dir

def test_full_service_worker_lifecycle(mock_integration_environment):
    """
    Tests complete integration cycle:
    1. Small file under 20MB -> Sent directly
    2. Check again -> Skipped (duplicate)
    3. Large file over 20MB -> Compressed, split into multi-part zip, all parts sent
    4. Temp directory cleaned up
    5. Check again -> Skipped
    """
    monitored_dir, temp_dir = mock_integration_environment

    # --- Phase 1: Small file under 20MB ---
    f1 = monitored_dir / "small_report.pdf"
    f1.write_bytes(b"%PDF-1.4 Small document content" * 100)

    with patch("service_worker.broadcast_document") as mock_broadcast:
        # Mock successful send to both users
        mock_broadcast.return_value = {
            "1001": (True, "ok"),
            "1002": (True, "ok")
        }

        service_worker.perform_check()

        # broadcast_document should be called once for the single file
        assert mock_broadcast.call_count == 1
        args, _ = mock_broadcast.call_args
        assert args[2] == str(f1.resolve())  # Sent original file path

        # File must be recorded in state
        state = load_state()
        assert state["last_file_name"] == "small_report.pdf"

    # --- Phase 2: Duplicate check ---
    with patch("service_worker.broadcast_document") as mock_broadcast:
        service_worker.perform_check()
        # Must NOT call broadcast again
        mock_broadcast.assert_not_called()

    # --- Phase 3: Large file over 20MB ---
    time.sleep(1.05)
    f2 = monitored_dir / "large_database.bak"
    # Create non-compressible data to guarantee size > 20MB
    f2.write_bytes(os.urandom(22 * 1024 * 1024))  # 22 MB

    with patch("service_worker.broadcast_document") as mock_broadcast:
        mock_broadcast.return_value = {
            "1001": (True, "ok"),
            "1002": (True, "ok")
        }

        service_worker.perform_check()

        # Since file is 22MB and chunk size is 10MB, it is split into 3 parts
        # Therefore broadcast_document must be called for each part
        assert mock_broadcast.call_count == 3
        
        # Verify parts were .zip.001, .zip.002, .zip.003
        call1_args, _ = mock_broadcast.call_args_list[0]
        call2_args, _ = mock_broadcast.call_args_list[1]
        call3_args, _ = mock_broadcast.call_args_list[2]
        assert call1_args[2].endswith(".001")
        assert call2_args[2].endswith(".002")
        assert call3_args[2].endswith(".003")

        # State must now record the large file
        state2 = load_state()
        assert state2["last_file_name"] == "large_database.bak"

    # --- Phase 4: Verify temp folder is cleaned up ---
    assert not temp_dir.exists() or len(list(temp_dir.iterdir())) == 0

    # --- Phase 5: Check again -> No sending ---
    with patch("service_worker.broadcast_document") as mock_broadcast:
        service_worker.perform_check()
        mock_broadcast.assert_not_called()

def test_send_once_and_wait_for_new_file(mock_integration_environment):
    """
    Verifies that:
    1. A file is sent only once.
    2. Repeated checks do NOT send it again (waiting mode).
    3. Only when a brand new file appears, sending occurs again for the new file.
    """
    monitored_dir, _ = mock_integration_environment

    f1 = monitored_dir / "backup_v1.bak"
    f1.write_bytes(b"Backup Version 1 content")

    with patch("service_worker.broadcast_document") as mock_broadcast:
        mock_broadcast.return_value = {"1001": (True, "ok"), "1002": (True, "ok")}

        # First check -> Sends f1
        assert service_worker.perform_send() is True
        assert mock_broadcast.call_count == 1

        # Second check -> File already sent, must NOT send again
        assert service_worker.perform_send() is False
        assert mock_broadcast.call_count == 1  # Still 1, not called again

        # Third check -> Still no new file, must NOT send again
        assert service_worker.perform_send() is False
        assert mock_broadcast.call_count == 1

        # Now add a NEW file
        time.sleep(1.05)
        f2 = monitored_dir / "backup_v2.bak"
        f2.write_bytes(b"Backup Version 2 content")

        # Fourth check -> New file detected, must send f2 ONCE
        assert service_worker.perform_send() is True
        assert mock_broadcast.call_count == 2
        args, _ = mock_broadcast.call_args
        assert args[2] == str(f2.resolve())

        # Fifth check -> Already sent f2, must NOT send again
        assert service_worker.perform_send() is False
        assert mock_broadcast.call_count == 2

def test_multipart_aborts_immediately_on_first_part_failure(mock_integration_environment):
    """
    Verifies that if Part 1 fails, remaining parts (Part 2, 3...) are NOT sent,
    preventing duplicate/partial deliveries to the user on Bale.
    """
    monitored_dir, _ = mock_integration_environment
    large_file = monitored_dir / "large_dataset.dat"
    large_file.write_bytes(os.urandom(25 * 1024 * 1024))  # 25 MB -> splits into multiple parts

    with patch("service_worker.broadcast_document") as mock_broadcast:
        # Simulate Part 1 failing
        mock_broadcast.return_value = {
            "1001": (False, "Network connection write timed out")
        }

        success = service_worker.perform_send()
        assert success is False
        # Crucial check: broadcast_document should only be called ONCE (for part 1) and abort!
        assert mock_broadcast.call_count == 1
        args, _ = mock_broadcast.call_args
        assert args[2].endswith(".001")

def test_arrival_announcement_and_progress_reports_sent_to_bale_user(mock_integration_environment):
    """
    Verifies that when a file is detected:
    1. Arrival notification is broadcast to user in Bale (file name, size, parts, compression).
    2. Document is uploaded with progress callback.
    3. Final completion summary is sent.
    """
    monitored_dir, _ = mock_integration_environment
    test_f = monitored_dir / "financial_data.xlsx"
    test_f.write_bytes(b"Spreadsheet content" * 50)

    broadcast_messages = []
    def fake_broadcast_msg(token, uids, text):
        broadcast_messages.append(text)
        return {uid: (True, "ok") for uid in uids}

    with patch("service_worker.broadcast_message", side_effect=fake_broadcast_msg) as mock_bmsg, \
         patch("service_worker.broadcast_document") as mock_bdoc:

        mock_bdoc.return_value = {"1001": (True, "ok"), "1002": (True, "ok")}

        ok = service_worker.perform_send()
        assert ok is True

        # 1. Arrival announcement check
        assert len(broadcast_messages) >= 2
        arrival_text = broadcast_messages[0]
        assert "فایل جدید در سیستم دریافت شد" in arrival_text
        assert "financial_data.xlsx" in arrival_text
        assert "حجم اصلی فایل" in arrival_text
        assert "ساختار ارسال" in arrival_text

        # 2. Document upload check
        assert mock_bdoc.call_count == 1
        doc_kwargs = mock_bdoc.call_args[1]
        assert "progress_callback" in doc_kwargs
        assert doc_kwargs["progress_callback"] is not None

        # 3. Completion summary check
        completion_text = broadcast_messages[-1]
        assert "ارسال کامل فایل" in completion_text
        assert "financial_data.xlsx" in completion_text
        assert "تعداد پارت‌ها" in completion_text

        # 4. Verify file remains safely intact on disk after successful completion
        assert test_f.exists()

def test_adaptive_part_size_in_service_worker(mock_integration_environment):
    """
    Verifies that service_worker dynamically chooses:
    - 10MB parts when upload speed is < 0.5 MB/s
    - 20MB parts when upload speed is >= 0.5 MB/s
    """
    monitored_dir, _ = mock_integration_environment
    from core.state_manager import set_last_upload_speed

    # 1. Test fast connection: 1.5 MB/s (>= 0.5 MB/s)
    set_last_upload_speed(1.5 * 1024 * 1024)
    f_fast = monitored_dir / "fast_file.bin"
    f_fast.write_bytes(os.urandom(25 * 1024 * 1024))  # 25 MB

    with patch("service_worker.broadcast_document") as mock_bdoc:
        mock_bdoc.return_value = {"1001": (True, "ok"), "1002": (True, "ok")}
        service_worker.perform_send()

        # With 20MB parts, 25MB file creates 2 parts (20MB, 5MB)
        assert mock_bdoc.call_count == 2
        # Verify file is preserved safely
        assert f_fast.exists()

    # 2. Test slow connection: 0.2 MB/s (< 0.5 MB/s)
    set_last_upload_speed(0.2 * 1024 * 1024)
    f_slow = monitored_dir / "slow_file.bin"
    f_slow.write_bytes(os.urandom(25 * 1024 * 1024))  # 25 MB

    with patch("service_worker.broadcast_document") as mock_bdoc:
        mock_bdoc.return_value = {"1001": (True, "ok"), "1002": (True, "ok")}
        service_worker.perform_send()

        # With 10MB parts, 25MB file creates 3 parts (10MB, 10MB, 5MB)
        assert mock_bdoc.call_count == 3
        # Verify file is preserved safely
        assert f_slow.exists()

def test_initial_folder_configuration_ignores_existing_files(mock_integration_environment):
    """
    Verifies that when a folder with pre-existing files is configured/monitored,
    existing files are baselined and NOT sent. The service must wait for a NEW file.
    """
    monitored_dir, _ = mock_integration_environment
    from core.state_manager import is_folder_baselined, baseline_folder_contents

    # 1. Folder already has an old file before configuration
    old_f = monitored_dir / "old_pre_existing_backup.bak"
    old_f.write_bytes(b"Old backup content before Axis Puls was configured")

    assert is_folder_baselined(str(monitored_dir)) is False

    # 2. Simulate initial configuration baselining
    base_file = baseline_folder_contents(str(monitored_dir))
    assert base_file is not None
    assert base_file["name"] == "old_pre_existing_backup.bak"
    assert is_folder_baselined(str(monitored_dir)) is True

    # 3. Check that perform_send does NOT send the pre-existing file
    with patch("service_worker.broadcast_document") as mock_bdoc:
        result = service_worker.perform_send()
        assert result is False
        mock_bdoc.assert_not_called()
        # Old file must NOT be deleted
        assert old_f.exists()

    # 4. A truly NEW file arrives later
    time.sleep(1.05)
    new_f = monitored_dir / "new_backup_generated_now.bak"
    new_f.write_bytes(b"New database backup content generated just now")

    with patch("service_worker.broadcast_document") as mock_bdoc:
        mock_bdoc.return_value = {"1001": (True, "ok"), "1002": (True, "ok")}
        result = service_worker.perform_send()
        assert result is True
        mock_bdoc.assert_called_once()
        # Verify new file was delivered and preserved on disk
        assert new_f.exists()


