import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json

from core.version import get_current_version, is_newer_version
from core.github_updater import (
    check_for_github_update,
    download_github_release_asset,
    publish_new_release
)

def test_version_comparisons():
    assert is_newer_version("1.0.1", "1.0.0") is True
    assert is_newer_version("v1.2.0", "1.1.9") is True
    assert is_newer_version("2.0.0", "1.9.9") is True
    assert is_newer_version("1.0.0", "1.0.0") is False
    assert is_newer_version("0.9.9", "1.0.0") is False
    assert is_newer_version("invalid", "1.0.0") is False

def test_check_for_github_update_no_update():
    fake_release = {
        "tag_name": "v1.0.0",
        "name": "Release 1.0.0",
        "body": "Initial release",
        "assets": [
            {
                "name": "AxisPuls_Setup.exe",
                "browser_download_url": "https://github.com/axispuls/axispuls1/releases/download/v1.0.0/AxisPuls_Setup.exe",
                "size": 52428800
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_release).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("core.github_updater.get_current_version", return_value="1.0.0"):
        res = check_for_github_update("axispuls", "axispuls1")
        assert res["ok"] is True
        assert res["has_update"] is False
        assert res["latest_version"] == "v1.0.0"
        assert res["asset_size_mb"] == 50.0

def test_check_for_github_update_has_update():
    fake_release = {
        "tag_name": "v1.1.0",
        "name": "Release 1.1.0",
        "body": "Big update with new features",
        "assets": [
            {
                "name": "AxisPuls_Setup.exe",
                "browser_download_url": "https://github.com/axispuls/axispuls1/releases/download/v1.1.0/AxisPuls_Setup.exe",
                "size": 55000000
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_release).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("core.github_updater.get_current_version", return_value="1.0.0"):
        res = check_for_github_update("axispuls", "axispuls1")
        assert res["ok"] is True
        assert res["has_update"] is True
        assert res["latest_version"] == "v1.1.0"
        assert res["download_url"] == "https://github.com/axispuls/axispuls1/releases/download/v1.1.0/AxisPuls_Setup.exe"

def test_download_github_release_asset_success(tmp_path):
    target = tmp_path / "downloaded.exe"
    # Construct valid mock PE file
    fake_content = b"MZ" + b"\x00" * (105 * 1024)

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [fake_content, b""]
    mock_resp.headers = {"Content-Length": str(len(fake_content))}
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = download_github_release_asset("https://fake.url/download.exe", target)
        assert ok is True
        assert target.exists()
