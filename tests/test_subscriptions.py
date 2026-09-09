from datetime import datetime, timedelta, timezone
import json
import pytest
from unittest.mock import Mock, patch

from src.user_configuration import LocalUserConfiguration
from src.access_control import get_effective_plan, get_effective_alert_limit
from src.telegram import TelegramBot
from src.alert_processes.cex import CEXAlertProcess


@pytest.fixture
def mock_config(tmp_path):
    root = tmp_path / "whitelist"
    root.mkdir()
    user_dir = root / "123"
    user_dir.mkdir()

    config_file = user_dir / "config.json"
    alerts_file = user_dir / "alerts.json"

    config_data = {
        "channels": ["123"],
        "plan": "pro",
        "max_alerts": 30,
        "plan_expiration": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }

    with open(config_file, "w") as f:
        json.dump(config_data, f)

    alerts_data = {
        "BTC/USDT": [
            {"type": "s", "indicator": "PRICE"},
            {"type": "s", "indicator": "PRICE"},
            {"type": "s", "indicator": "PRICE"},
            {"type": "s", "indicator": "PRICE"},
        ]
    }
    with open(alerts_file, "w") as f:
        json.dump(alerts_data, f)

    with patch("src.user_configuration.WHITELIST_ROOT", str(root)):
        yield LocalUserConfiguration("123")


def test_effective_plan_expired(mock_config):
    config = mock_config.load_config()
    assert get_effective_plan(config) == "free"
    assert get_effective_alert_limit(config) == 3
    # Original config is intact
    assert config["plan"] == "pro"


def test_effective_plan_active(mock_config):
    config = mock_config.load_config()
    config["plan_expiration"] = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat()
    assert get_effective_plan(config) == "pro"
    assert get_effective_alert_limit(config) == 30


def test_activate_plan_adds_days(mock_config):
    mock_config.activate_plan("pro", 30, "/admin_activate 123 pro 30", 1)

    config = mock_config.load_config()
    assert config["plan"] == "pro"

    expiration = datetime.fromisoformat(config["plan_expiration"])
    assert expiration > datetime.now(timezone.utc) + timedelta(days=29)
    assert expiration < datetime.now(timezone.utc) + timedelta(days=31)


def test_activate_plan_replay_protection(mock_config):
    mock_config.activate_plan("pro", 30, "/admin_activate 123 pro 30", 1)
    with pytest.raises(Exception):
        mock_config.activate_plan("pro", 30, "/admin_activate 123 pro 30", 1)


def test_keeping_first_3_alerts(mock_config, mocker):
    bot = Mock()
    bot.send_message.return_value = True
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="dummy")

    process = CEXAlertProcess(bot)
    process.tg_alert = Mock(return_value=([123], []))
    process.get_simple_indicator = Mock(return_value=(True, 0.05, "post"))

    # Process relies on access_control internally which works correctly.
    with patch(
        "src.alert_processes.cex.LocalUserConfiguration", return_value=mock_config
    ):
        process.poll_user_alerts("123")

    assert process.get_simple_indicator.call_count == 3
