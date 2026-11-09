import time
import pytest
from unittest.mock import patch, MagicMock

from core.license_notifier import (
    check_and_send_license_alerts,
    load_alert_state,
    save_alert_state,
    get_all_target_chat_ids,
    TRIAL_DANGER_TEMPLATES,
    EXPIRED_IMMEDIATE_TEMPLATES,
    EXPIRED_DAILY_TEMPLATES,
    EXPIRED_WEEKLY_TEMPLATES
)

def test_get_all_target_chat_ids():
    targets = get_all_target_chat_ids()
    assert isinstance(targets, list)
    assert "1147503382" in targets

def test_rotating_templates_distinct():
    assert len(TRIAL_DANGER_TEMPLATES) >= 4
    assert len(EXPIRED_IMMEDIATE_TEMPLATES) >= 3
    assert len(EXPIRED_DAILY_TEMPLATES) >= 3
    assert len(EXPIRED_WEEKLY_TEMPLATES) >= 2

    # Verify all templates contain support ID
    for tmpl in TRIAL_DANGER_TEMPLATES + EXPIRED_IMMEDIATE_TEMPLATES:
        assert "@AXISPULS" in tmpl

@patch("core.license_notifier.broadcast_message_async")
@patch("core.license_notifier.load_config")
@patch("core.license_notifier.is_license_active")
def test_alert_during_trial(mock_is_active, mock_cfg, mock_broadcast, tmp_path):
    mock_cfg.return_value = {"bot_token": "fake_token", "user_ids": ["123"]}
    now = time.time()
    # Trial active, activated 30 hours ago, expires in 42 hours
    mock_is_active.return_value = (
        True,
        "Active",
        {
            "plan_id": "trial_72h",
            "activated_at_epoch": now - (30 * 3600),
            "expires_at": now + (42 * 3600),
            "time_rem_str": "1 روز و 18 ساعت"
        }
    )

    state = load_alert_state()
    state["last_alert_epoch"] = now - (7 * 3600)  # >6 hours ago
    save_alert_state(state)

    stage = check_and_send_license_alerts()
    assert stage is not None
    assert "trial_active_6h" in stage
    assert mock_broadcast.called
