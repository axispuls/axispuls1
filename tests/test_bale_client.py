import time
import pytest
import requests
from unittest.mock import patch, MagicMock
from core.bale_client import (
    get_bot_info,
    send_message,
    send_message_async,
    broadcast_message_async,
    send_document,
    broadcast_document,
    broadcast_message,
    verify_bot_token_and_username
)

def test_get_bot_info_success():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {
                "first_name": "تست بات",
                "username": "test_bot"
            }
        }
        mock_get.return_value = mock_response

        ok, msg, data = get_bot_info("123456:valid_token")
        assert ok is True
        assert "تست بات" in msg
        assert data["username"] == "test_bot"

def test_get_bot_info_invalid():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "ok": False,
            "error_code": 401,
            "description": "Unauthorized"
        }
        mock_get.return_value = mock_response

        ok, msg, data = get_bot_info("123456:invalid_token")
        assert ok is False
        assert "401" in msg

def test_send_message_success():
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        ok, msg = send_message("token", "12345", "test message")
        assert ok is True
        assert "با موفقیت" in msg

def test_send_document_file_not_found():
    ok, msg = send_document("token", "12345", "non_existing_file_9876.zip")
    assert ok is False
    assert "یافت نشد" in msg

def test_send_document_success(tmp_path):
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4 test")

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        ok, msg = send_document("token", "12345", str(doc), caption="test caption")
        assert ok is True
        assert "با موفقیت" in msg

def test_broadcast_document(tmp_path):
    doc = tmp_path / "broadcast.pdf"
    doc.write_bytes(b"content")

    with patch("core.bale_client.send_document") as mock_send_doc:
        mock_send_doc.side_effect = [
            (True, "ok"),
            (False, "failed")
        ]
        results = broadcast_document("token", ["101", "102"], str(doc))
        assert results["101"][0] is True
        assert results["102"][0] is False

def test_verify_bot_token_and_username_matching():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {
                "first_name": "ربات بکاپ من",
                "username": "my_backup_bot"
            }
        }
        mock_get.return_value = mock_response

        # Matches with @
        ok1, msg1, data1 = verify_bot_token_and_username("test_tok", "@my_backup_bot")
        assert ok1 is True
        assert "my_backup_bot" in msg1

        # Matches without @ and case-insensitive
        ok2, msg2, data2 = verify_bot_token_and_username("test_tok", "MY_BACKUP_BOT")
        assert ok2 is True

def test_verify_bot_token_and_username_mismatch():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {
                "first_name": "ربات بکاپ من",
                "username": "actual_bot"
            }
        }
        mock_get.return_value = mock_response

        ok, msg, data = verify_bot_token_and_username("test_tok", "@different_bot")
        assert ok is False
        assert "عدم تطابق" in msg
        assert "@different_bot" in msg
        assert "@actual_bot" in msg

def test_send_message_async():
    with patch("core.bale_client.send_message") as mock_send:
        mock_send.return_value = (True, "ok")
        send_message_async("token123", "999", "Async hello")
        # Give thread a moment
        time.sleep(0.1)
        mock_send.assert_called_once_with("token123", "999", "Async hello")

def test_send_document_with_progress_milestones(tmp_path):
    test_file = tmp_path / "big_report.dat"
    test_file.write_bytes(b"A" * 50000)

    progress_milestones = []
    def on_prog(pct, b_read, b_tot):
        progress_milestones.append(pct)

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99}}
        mock_post.return_value = mock_resp

        ok, msg = send_document(
            "token",
            "1001",
            str(test_file),
            caption="test",
            progress_callback=on_prog
        )
        assert ok is True
        assert 100 in progress_milestones

def test_send_message_with_id_and_delete_message():
    from core.bale_client import send_message_with_id, delete_message, delete_messages_async

    with patch("requests.post") as mock_post:
        # 1. Test send_message_with_id
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 5544}}
        mock_post.return_value = mock_resp

        ok, msg, m_id = send_message_with_id("token123", "999", "Test with ID")
        assert ok is True
        assert m_id == 5544

        # 2. Test delete_message
        del_resp = MagicMock()
        del_resp.status_code = 200
        del_resp.json.return_value = {"ok": True, "result": True}
        mock_post.return_value = del_resp

        del_ok = delete_message("token123", "999", 5544)
        assert del_ok is True
        # Verify /deleteMessage was called with correct payload
        args, kwargs = mock_post.call_args
        assert "/deleteMessage" in args[0]
        assert kwargs["json"] == {"chat_id": "999", "message_id": 5544}

