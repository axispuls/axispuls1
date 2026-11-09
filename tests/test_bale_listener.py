import pytest
from unittest.mock import patch, MagicMock
from core.bale_listener import (
    build_welcome_message,
    record_user_start,
    load_registered_users,
    save_registered_users,
    BaleBotListener
)

@pytest.fixture(autouse=True)
def mock_users_file(tmp_path):
    mock_file = tmp_path / "mock_registered_users.json"
    with patch("core.bale_listener.REGISTERED_USERS_FILE", mock_file):
        yield mock_file

def test_welcome_message_format():
    user_id = 987654321
    # Test for new / unknown user
    msg_new = build_welcome_message(user_id, "رضا", is_known_user=False)
    assert "رضا" in msg_new
    assert f"`{user_id}`" in msg_new
    assert "شناسه عددی شما" in msg_new
    assert "@AXISPULS" in msg_new
    assert "بکاپ" in msg_new
    assert "اکسیس پالس" in msg_new

    # Test for authorized user
    msg_known = build_welcome_message(user_id, "رضا", is_known_user=True)
    assert f"`{user_id}`" in msg_known
    assert "کاربران مجاز" in msg_known
    assert "@AXISPULS" in msg_known

def test_record_user_start():
    record_user_start(1001, "علی", "ali_user")
    users = load_registered_users()
    assert len(users) == 1
    assert users[0]["user_id"] == 1001
    assert users[0]["first_name"] == "علی"
    assert users[0]["username"] == "ali_user"

    # Updating same user should not create a duplicate
    record_user_start(1001, "علی جدید", "ali_user")
    users_after = load_registered_users()
    assert len(users_after) == 1
    assert users_after[0]["first_name"] == "علی جدید"

def test_process_start_update():
    listener = BaleBotListener("12345:dummy_token")
    mock_callback = MagicMock()
    listener.on_user_start = mock_callback

    update = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "from": {
                "id": 556677,
                "first_name": "سارا",
                "username": "sara_k"
            },
            "chat": {
                "id": 556677
            },
            "text": "/start"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send:
        mock_send.return_value = (True, "sent")
        listener._process_single_update(update)

        # Must record user
        users = load_registered_users()
        assert any(u["user_id"] == 556677 for u in users)

        # Must send message to user with their ID
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert args[1] == "556677"
        assert "`556677`" in args[2]

        # Must trigger callback
        mock_callback.assert_called_once()

def test_process_non_start_ignored():
    listener = BaleBotListener("12345:dummy_token")
    update = {
        "update_id": 43,
        "message": {
            "from": {"id": 12345},
            "text": "سلام خسته نباشید"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send:
        listener._process_single_update(update)
        mock_send.assert_not_called()

def test_super_admin_menu_commands():
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    update = {
        "update_id": 100,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "/start"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send:
        listener._process_single_update(update)
        assert mock_send.call_count == 2
        first_call = mock_send.call_args_list[0]
        second_call = mock_send.call_args_list[1]
        assert first_call[0][1] == str(SUPER_ADMIN_ID)
        assert "مدیر گرامی" in first_call[0][2]
        assert "keyboard" in first_call[1]["reply_markup"]
        assert "inline_keyboard" in second_call[1]["reply_markup"]

def test_super_admin_hardware_command():
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    update = {
        "update_id": 101,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "/hardware"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.collect_hardware_fingerprint") as mock_hw, \
         patch("core.bale_listener.format_hardware_report", return_value="MOCK_HW_REPORT"):
        mock_hw.return_value = {"persistent_hw_hash": "AXIS-TEST1234"}
        listener._process_single_update(update)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "12345:dummy_token"
        assert args[1] == str(SUPER_ADMIN_ID)
        assert args[2] == "MOCK_HW_REPORT"
        assert kwargs.get("reply_markup") is not None

def test_super_admin_remote_activate():
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    update = {
        "update_id": 102,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "/activate 1y"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.activate_plan_directly") as mock_act, \
         patch("core.bale_listener.broadcast_message_async"):
        mock_act.return_value = (True, "OK", {
            "plan_title": "اشتراک ۱ ساله (۵ میلیون تومان)",
            "expires_at_str": "2027-11-09 00:00:00"
        })
        listener._process_single_update(update)
        mock_act.assert_called_once_with("plan_1y", custom_days=None, activated_by=f"admin_{SUPER_ADMIN_ID}")
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][2]
        assert "موفقیت فعال گردید" in sent_text
        assert "۱ ساله" in sent_text

def test_super_admin_remote_extend():
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    update = {
        "update_id": 103,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "/extend 60"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.extend_license_days") as mock_ext, \
         patch("core.bale_listener.broadcast_message_async"):
        mock_ext.return_value = (True, "OK", {
            "plan_title": "تمدید شده (۶۰ روز)",
            "expires_at_str": "2027-01-09 00:00:00"
        })
        listener._process_single_update(update)
        mock_ext.assert_called_once_with(60, activated_by=f"admin_{SUPER_ADMIN_ID}")
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][2]
        assert "تمدید شد" in sent_text

def test_super_admin_reply_keyboard_button_press():
    """Tapping Persian Reply Keyboard buttons executes the corresponding action directly."""
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    # 1. Tapping '⭐ فعال‌سازی ۱ ساله' button
    update_1y = {
        "update_id": 104,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "⭐ فعال‌سازی ۱ ساله"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.activate_plan_directly") as mock_act, \
         patch("core.bale_listener.broadcast_message_async"):
        mock_act.return_value = (True, "OK", {
            "plan_title": "اشتراک ۱ ساله (۵ میلیون تومان)",
            "expires_at_str": "2027-11-09 00:00:00"
        })
        listener._process_single_update(update_1y)
        mock_act.assert_called_once_with("plan_1y", custom_days=None, activated_by=f"admin_{SUPER_ADMIN_ID}")
        assert "۱ ساله" in mock_send.call_args[0][2]

def test_super_admin_inline_callback_query():
    """Clicking an inline button (callback_query) executes the corresponding action."""
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    cq_update = {
        "update_id": 105,
        "callback_query": {
            "id": "cq_999",
            "from": {"id": SUPER_ADMIN_ID},
            "data": "cmd_act_10y"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.answer_callback_query") as mock_ans, \
         patch("core.bale_listener.activate_plan_directly") as mock_act, \
         patch("core.bale_listener.broadcast_message_async"):
        mock_act.return_value = (True, "OK", {
            "plan_title": "اشتراک ۱۰ ساله (۲۰ میلیون تومان)",
            "expires_at_str": "2036-11-09 00:00:00"
        })
        listener._process_single_update(cq_update)
        mock_ans.assert_called_once_with("12345:dummy_token", "cq_999")
        mock_act.assert_called_once_with("plan_10y", custom_days=None, activated_by=f"admin_{SUPER_ADMIN_ID}")
        assert "۱۰ ساله" in mock_send.call_args[0][2]

def test_super_admin_update_button_and_prompt():
    """Tapping '📤 ارسال آخرین نسخه' prompts the admin with update instructions and options."""
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    update_btn = {
        "update_id": 106,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "text": "📤 ارسال آخرین نسخه"
        }
    }

    with patch("core.bale_listener.send_message") as mock_send:
        listener._process_single_update(update_btn)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[1] == str(SUPER_ADMIN_ID)
        assert "به‌روزرسانی خودکار" in args[2]
        assert "inline_keyboard" in kwargs.get("reply_markup", {})

def test_super_admin_incoming_document_triggers_update():
    """When Super Admin sends an executable document, the listener downloads and applies self-update."""
    from core.license_manager import SUPER_ADMIN_ID
    listener = BaleBotListener("12345:dummy_token")

    doc_update = {
        "update_id": 107,
        "message": {
            "from": {"id": SUPER_ADMIN_ID},
            "document": {
                "file_id": "file_test_123",
                "file_name": "AxisPuls_Setup.exe",
                "file_size": 53260000
            }
        }
    }

    with patch("core.bale_listener.send_message") as mock_send, \
         patch("core.bale_listener.download_file", return_value=(True, "Downloaded OK")) as mock_dl, \
         patch("core.self_updater.apply_update_and_restart", return_value=(True, "Relaunching")) as mock_apply:
        listener._process_single_update(doc_update)
        mock_dl.assert_called_once()
        mock_apply.assert_called_once()
        # Verify status messages sent to admin
        assert mock_send.call_count >= 2



