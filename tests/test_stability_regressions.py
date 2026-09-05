import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.access_control import get_effective_alert_limit, iter_eligible_alerts
from src.alert_processes.cex import CEXAlertProcess
from src.indicators import TADatabaseClient, TaapiioProcess
from src.telegram import parse_technical_alert_arguments


def test_default_alerts_are_empty_for_new_users():
    default_alerts = Path("src/resources/default_alerts.json")
    assert json.loads(default_alerts.read_text(encoding="utf-8")) == {}


def test_free_plan_selects_only_first_three_alerts():
    alerts = {
        "BTC/USDT": [{"id": 1}, {"id": 2}],
        "ETH/USDT": [{"id": 3}, {"id": 4}],
    }

    limit = get_effective_alert_limit({"plan": "free"})
    eligible = list(iter_eligible_alerts(alerts, limit))

    assert [(pair, alert["id"]) for pair, _, alert in eligible] == [
        ("BTC/USDT", 1),
        ("BTC/USDT", 2),
        ("ETH/USDT", 3),
    ]


def test_cex_worker_does_not_evaluate_alerts_beyond_plan_quota(mocker):
    alerts = {
        "BTC/USDT": [
            {
                "type": "s",
                "trigger": {"cooldown_seconds": 60, "last_triggered": 0},
            }
            for _ in range(4)
        ]
    }
    configuration = Mock()
    configuration.load_alerts.return_value = alerts
    configuration.load_config.return_value = {"plan": "free", "channels": ["1"]}
    mocker.patch(
        "src.alert_processes.cex.LocalUserConfiguration",
        return_value=configuration,
    )
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="unused")

    process = CEXAlertProcess(Mock())
    indicator = mocker.patch.object(
        process, "get_simple_indicator", return_value=(False, 100, "")
    )
    process.poll_user_alerts("1")

    assert indicator.call_count == 3


def test_technical_alert_accepts_optional_cooldown():
    parts = [
        "BTC/USDT",
        "RSI",
        "1h",
        "period=14",
        "value",
        "ABOVE",
        "70",
        "5m",
    ]

    required, cooldown = parse_technical_alert_arguments(parts)

    assert required == parts[:7]
    assert cooldown == "5m"


def test_technical_alert_rejects_extra_arguments():
    with pytest.raises(ValueError, match="7 arguments"):
        parse_technical_alert_arguments(["extra"] * 9)


def test_indicator_parameter_validation_accepts_named_params_and_output():
    client = TADatabaseClient()

    assert (
        client.validate_indicator("BBANDS", "period=20,stddev=2,output=valueUpperBand")
        is not None
    )
    assert client.validate_indicator("BBANDS", "unknown=2") is None
    assert client.validate_indicator("BBANDS", "output=unknown") is None


def test_taapi_run_restarts_without_recursion(mocker):
    process = TaapiioProcess("secret")
    mainloop = mocker.patch.object(
        process, "mainloop", side_effect=[RuntimeError("temporary"), KeyboardInterrupt]
    )
    mocker.patch.object(process, "alert_admins")
    sleep = mocker.patch("src.indicators.sleep")

    process.run()

    assert mainloop.call_count == 2
    sleep.assert_called_once_with(15)


def test_taapi_bulk_request_uses_timeout_without_logging_secret(mocker):
    process = TaapiioProcess("super-secret")
    response = Mock()
    response.json.return_value = {"data": []}
    post = mocker.patch("src.indicators.requests.post", return_value=response)
    log = mocker.patch("src.indicators.logger.info")

    process.call_api(
        "https://api.taapi.io/bulk",
        {"secret": "super-secret", "construct": {}},
    )

    assert post.call_args.kwargs["timeout"] == 15
    assert "super-secret" not in " ".join(
        str(value) for call in log.call_args_list for value in call.args
    )
