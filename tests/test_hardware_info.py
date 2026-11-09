import pytest
from unittest.mock import patch
from core.hardware_info import collect_hardware_fingerprint, format_hardware_report

def test_collect_hardware_fingerprint():
    hw = collect_hardware_fingerprint()
    assert isinstance(hw, dict)
    assert "computer_name" in hw
    assert "persistent_hw_hash" in hw
    assert hw["persistent_hw_hash"].startswith("AXIS-")
    assert len(hw["persistent_hw_hash"]) > 10

def test_format_hardware_report():
    mock_hw = {
        "computer_name": "TEST-PC",
        "user_name": "TestUser",
        "os_version": "Windows 11 Pro",
        "motherboard_model": "ASUS ROG STRIX B550",
        "motherboard_serial": "MB-12345678",
        "cpu_name": "AMD Ryzen 7 5800X",
        "cpu_id": "CPU-87654321",
        "system_uuid": "UUID-1111-2222-3333",
        "disks": [
            {"model": "Samsung 980 PRO 1TB", "serial": "S6B2NL0W123456", "size_gb": 1000.0}
        ],
        "primary_disk_serial": "S6B2NL0W123456",
        "mac_addresses": ["AA:BB:CC:DD:EE:FF (Ethernet)"],
        "primary_mac": "AA:BB:CC:DD:EE:FF",
        "persistent_hw_hash": "AXIS-A1B2C3D4E5F67890"
    }

    report = format_hardware_report(mock_hw)
    assert "TEST-PC" in report
    assert "MB-12345678" in report
    assert "S6B2NL0W123456" in report
    assert "AXIS-A1B2C3D4E5F67890" in report
    assert "تعویض ویندوز" in report
