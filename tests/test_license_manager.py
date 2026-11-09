import time
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.license_manager import (
    is_license_active,
    request_and_send_activation_code,
    verify_and_activate,
    get_machine_id,
    generate_10char_code,
    validate_iran_phone,
    get_pending_request_status,
    generate_signature
)

@pytest.fixture
def mock_license_env(tmp_path):
    lic_file = tmp_path / "mock_license.json"
    pending_file = tmp_path / "mock_pending.json"
    appdata_file = tmp_path / ".sys_pending"

    with patch("core.license_manager.LICENSE_FILE", lic_file), \
         patch("core.license_manager.PENDING_FILE", pending_file), \
         patch("core.license_manager._get_appdata_pending_path", return_value=appdata_file), \
         patch("core.license_manager._save_pending_to_registry_and_appdata") as mock_save_reg, \
         patch("core.license_manager._clear_pending_all") as mock_clear_reg, \
         patch("winreg.CreateKey"), \
         patch("winreg.SetValueEx"), \
         patch("winreg.OpenKey", side_effect=OSError("Registry mock bypass")):
        yield lic_file, pending_file

def test_initial_license_inactive(mock_license_env):
    active, msg, info = is_license_active()
    assert active is False
    assert "فعال‌سازی نشده" in msg

def test_phone_validation():
    ok, num = validate_iran_phone("09123456789")
    assert ok is True
    assert num == "09123456789"

    ok2, num2 = validate_iran_phone("+989123456789")
    assert ok2 is True
    assert num2 == "09123456789"

    ok_inv1, _ = validate_iran_phone("08123456789")
    assert ok_inv1 is False

    ok_inv2, _ = validate_iran_phone("1234")
    assert ok_inv2 is False

    ok_inv3, _ = validate_iran_phone("")
    assert ok_inv3 is False

def test_code_generation_format():
    code = generate_10char_code()
    assert len(code) == 10
    assert code.isalnum()
    assert code.isupper()

def test_activation_flow_success(mock_license_env):
    lic_file, pending_file = mock_license_env

    # 1. Request code for 1-year plan
    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1, "Value": "123456"}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        # Capture generated code
        with patch("core.license_manager.generate_10char_code", return_value="ABC234XYZ9"):
            ok, msg = request_and_send_activation_code("09123456789", plan_id="plan_1y")
            assert ok is True
            assert "با موفقیت ثبت شد" in msg
            assert "09123456789" in msg
            assert pending_file.exists()

            # Verify admin SMS had code, plan, and applicant phone
            mock_sms.send_by_base_number.assert_called_once_with(
                "ABC234XYZ9 پلن:1ساله(5م) کاربر:09123456789",
                "09922975101",
                545530
            )

    # 2. Try activating with wrong code
    ok_wrong, msg_wrong = verify_and_activate("WRONG12345")
    assert ok_wrong is False
    assert "صحیح نمی‌باشد" in msg_wrong

    # 3. Try activating with invalid length
    ok_inv, msg_inv = verify_and_activate("123")
    assert ok_inv is False
    assert "۱۰ کاراکتر" in msg_inv

    # 4. Activate with correct code
    ok_correct, msg_correct = verify_and_activate("ABC234XYZ9")
    assert ok_correct is True
    assert "۱ ساله" in msg_correct or "۳۶۵ روز" in msg_correct
    assert lic_file.exists()

    # 5. Verify license is now active
    active, msg_active, info = is_license_active()
    assert active is True
    assert info["remaining_days"] in (364, 365)
    assert info["plan_id"] == "plan_1y"

def test_activation_flow_72h_trial(mock_license_env):
    lic_file, pending_file = mock_license_env

    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        with patch("core.license_manager.generate_10char_code", return_value="TRIAL72H11"):
            ok, _ = request_and_send_activation_code("09123456789", plan_id="trial_72h")
            assert ok is True
            mock_sms.send_by_base_number.assert_called_once_with(
                "TRIAL72H11 پلن:رایگان 72ساعته کاربر:09123456789",
                "09922975101",
                545530
            )

    ok_act, msg_act = verify_and_activate("TRIAL72H11")
    assert ok_act is True
    assert "۷۲ ساعته" in msg_act

    active, _, info = is_license_active()
    assert active is True
    assert info["plan_id"] == "trial_72h"

def test_activation_flow_10y(mock_license_env):
    lic_file, pending_file = mock_license_env

    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        with patch("core.license_manager.generate_10char_code", return_value="TENYEARS99"):
            ok, _ = request_and_send_activation_code("09123456789", plan_id="plan_10y")
            assert ok is True
            mock_sms.send_by_base_number.assert_called_once_with(
                "TENYEARS99 پلن:10ساله(20م) کاربر:09123456789",
                "09922975101",
                545530
            )

    ok_act, msg_act = verify_and_activate("TENYEARS99")
    assert ok_act is True
    assert "۱۰ ساله" in msg_act

    active, _, info = is_license_active()
    assert active is True
    assert info["plan_id"] == "plan_10y"
    assert info["remaining_days"] > 3000

def test_24_hour_rate_limiting_and_reopen_retention(mock_license_env):
    lic_file, pending_file = mock_license_env

    # 1. First request succeeds
    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        with patch("core.license_manager.generate_10char_code", return_value="PREVCODE88"):
            ok1, _ = request_and_send_activation_code("09199998877", plan_id="plan_1y")
            assert ok1 is True

    # 2. Second request within 24 hours is strictly BLOCKED
    ok2, msg2 = request_and_send_activation_code("09199998877", plan_id="plan_1y")
    assert ok2 is False
    assert "قبلاً برای این سیستم" in msg2 or "ساعت دیگر" in msg2

    # 3. App reopen check: pending status returns previous request
    is_p, p_msg, rec = get_pending_request_status()
    assert is_p is True
    assert rec["user_phone"] == "09199998877"
    assert "تماس" in p_msg

    # 4. The previous code still works to activate the app!
    ok_act, msg_act = verify_and_activate("PREVCODE88")
    assert ok_act is True
    assert "۱ ساله" in msg_act or "۳۶۵ روز" in msg_act

def test_machine_mismatch_rejected(mock_license_env):
    lic_file, _ = mock_license_env

    # Create license for Machine A
    past_time = time.time() + 365*86400
    sess_id = "test-session"
    fake_machine = "0000000000000000000000000000000000000000000000000000000000000000"
    sig = generate_signature(fake_machine, past_time, sess_id)

    lic_data = {
        "status": "active",
        "machine_id": fake_machine,
        "session_id": sess_id,
        "expires_at": past_time,
        "signature": sig
    }
    lic_file.write_text(json.dumps(lic_data), encoding="utf-8")

    # If opened on Machine B (different fingerprint)
    active, msg, _ = is_license_active()
    assert active is False
    assert "دستگاه دیگری" in msg

def test_tampered_license_detected(mock_license_env):
    lic_file, pending_file = mock_license_env

    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        with patch("core.license_manager.generate_10char_code", return_value="TESTCODE12"):
            request_and_send_activation_code("09121112233", plan_id="plan_1y")
            verify_and_activate("TESTCODE12")

    assert is_license_active()[0] is True

    # Tamper with expiration date in file
    data = json.loads(lic_file.read_text(encoding="utf-8"))
    data["expires_at"] += 999999.0
    lic_file.write_text(json.dumps(data), encoding="utf-8")

    active, msg, _ = is_license_active()
    assert active is False
    assert "معتبر نیست" in msg

def test_expired_license(mock_license_env):
    lic_file, _ = mock_license_env

    m_id = get_machine_id()
    past_time = time.time() - 1000
    sess_id = "expired-uuid"
    sig = generate_signature(m_id, past_time, sess_id)

    lic_data = {
        "status": "active",
        "machine_id": m_id,
        "session_id": sess_id,
        "expires_at": past_time,
        "signature": sig
    }
    lic_file.write_text(json.dumps(lic_data), encoding="utf-8")

    active, msg, _ = is_license_active()
    assert active is False
    assert "به پایان رسیده است" in msg

def test_activate_plan_directly_and_extend(mock_license_env):
    from core.license_manager import activate_plan_directly, extend_license_days

    # 1. Direct activation of 72h
    ok, msg, data = activate_plan_directly("trial_72h")
    assert ok is True
    assert "۷۲ ساعته" in data["plan_title"]
    active, _, info = is_license_active()
    assert active is True
    assert info["remaining_days"] <= 3

    # 2. Direct activation of 1 year
    ok_1y, _, data_1y = activate_plan_directly("plan_1y")
    assert ok_1y is True
    assert "۱ ساله" in data_1y["plan_title"]
    active2, _, info2 = is_license_active()
    assert active2 is True
    assert info2["remaining_days"] >= 364

    # 3. Extend license by 30 days
    ok_ext, _, data_ext = extend_license_days(30)
    assert ok_ext is True
    active3, _, info3 = is_license_active()
    assert active3 is True
    assert info3["remaining_days"] >= 394

def test_send_admin_bot_id_sms():
    from core.license_manager import send_admin_bot_id_sms

    with patch("melipayamak.Api") as mock_api:
        mock_instance = MagicMock()
        mock_sms = MagicMock()
        mock_sms.send_by_base_number.return_value = {"RetStatus": 1}
        mock_instance.sms.return_value = mock_sms
        mock_api.return_value = mock_instance

        ok, err = send_admin_bot_id_sms("@MyBackupBot", plan_title="72h")
        assert ok is True
        mock_sms.send_by_base_number.assert_called_once_with(
            "ربات:@MyBackupBot فعالسازی72h",
            "09922975101",
            545530
        )

def test_reset_software_session(mock_license_env):
    from core.license_manager import activate_plan_directly, reset_software_session, is_license_active

    activate_plan_directly("trial_72h")
    act, _, _ = is_license_active()
    assert act is True

    ok, msg = reset_software_session()
    assert ok is True
    act_after, _, _ = is_license_active()
    assert act_after is False

