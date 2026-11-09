import os
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.setup_sender import send_application_setup, SAFE_SETUP_PART_SIZE
from core.archiver import extract_executable_from_zip

def test_extract_executable_from_zip(tmp_path):
    zip_path = tmp_path / "test_archive.zip"
    extracted_dir = tmp_path / "extracted"

    # Create dummy zip with an exe inside
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("AxisPuls_Setup.exe", b"MZ" + b"\x00" * 1024)
        zf.writestr("readme.txt", "Some notes")

    exe_path = extract_executable_from_zip(str(zip_path), str(extracted_dir))
    assert exe_path is not None
    assert Path(exe_path).exists()
    assert Path(exe_path).name == "AxisPuls_Setup.exe"

def test_send_application_setup_splits_large_exe(tmp_path):
    # Simulate 25 MB executable (> 20 MB Bale limit)
    fake_exe = tmp_path / "AxisPuls_Setup.exe"
    fake_exe.write_bytes(os.urandom(25 * 1024 * 1024))

    mock_temp_dir = tmp_path / "temp_setup"
    part_sizes = []

    def _mock_doc(tok, cid, path, **kwargs):
        part_sizes.append(os.path.getsize(path))
        return True, "OK"

    with patch("core.setup_sender.get_current_executable_path", return_value=fake_exe), \
         patch("core.setup_sender.SETUP_TEMP_DIR", mock_temp_dir), \
         patch("core.setup_sender.send_message") as mock_msg, \
         patch("core.setup_sender.send_document", side_effect=_mock_doc) as mock_doc:

        ok, msg = send_application_setup("123:token", ["1001", "1002"])
        assert ok is True
        assert "موفقیت" in msg

        # With 18 MB part size and ~25 MB data, parts are generated and sent via send_document
        assert mock_doc.call_count >= 2

        # Check part file sizes: EVERY PART sent MUST BE <= 18 MB (strictly under 20 MB limit!)
        assert len(part_sizes) >= 2
        for sz in part_sizes:
            assert sz <= SAFE_SETUP_PART_SIZE

        # Final message with extraction instructions must be sent
        assert mock_msg.call_count >= 2
        last_msg = mock_msg.call_args_list[-1][0][2]
        assert "استخراج" in last_msg or "پارت" in last_msg

def test_bale_listener_handles_zip_update(tmp_path):
    from core.bale_listener import BaleBotListener
    from core.license_manager import SUPER_ADMIN_ID

    listener = BaleBotListener("123:token")

    # Create dummy update zip
    zip_update = tmp_path / "update_pkg.zip"
    with zipfile.ZipFile(zip_update, "w") as zf:
        zf.writestr("AxisPuls_Setup.exe", b"MZ" + b"\x00" * (120 * 1024))

    doc = {
        "file_id": "zip_file_99",
        "file_name": "update_pkg.zip",
        "file_size": 150000
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.download_file", return_value=(True, "OK")) as mock_dl, \
         patch("core.self_updater.UPDATE_DIR", tmp_path), \
         patch("core.self_updater.apply_update_and_restart", return_value=(True, "Restarting")) as mock_apply:

        # Mock download_file to write the actual zip to destination
        def _mock_dl(tok, fid, dest):
            import shutil
            shutil.copy(zip_update, dest)
            return True, "OK"

        mock_dl.side_effect = _mock_dl

        listener._handle_admin_incoming_document(doc, SUPER_ADMIN_ID, {})
        mock_apply.assert_called_once()
        applied_file = mock_apply.call_args[0][0]
        assert Path(applied_file).name == "AxisPuls_Setup.exe"
