import pytest
from src.alert_logic import AlertCooldownManager, calculate_rsi
from unittest.mock import Mock

from src.alert_processes.cex import CEXAlertProcess


def test_alert_logic_24hrchg_target(mocker):
    bot = Mock()
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="dummy")
    process = CEXAlertProcess(bot)
    alert = {"target": 0.05, "comparison": "24HRCHG"}
    mock_fetch = mocker.patch(
        "src.alert_processes.cex.fetch_binance_market_data",
        return_value={"lastPrice": 100, "priceChangePercent": 0.10},
    )
    triggered, _, _ = process.get_simple_indicator("BTC/USDT", alert, pair_price=100)
    assert not triggered
    mock_fetch.return_value = {"lastPrice": 100, "priceChangePercent": 5.0}
    triggered, _, _ = process.get_simple_indicator("BTC/USDT", alert, pair_price=100)
    assert triggered
    mock_fetch.return_value = {"lastPrice": 100, "priceChangePercent": -5.0}
    triggered, _, _ = process.get_simple_indicator("BTC/USDT", alert, pair_price=100)
    assert triggered


def test_cooldown_behavior(mocker):
    bot = Mock()
    bot.send_message.return_value = True
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="dummy")
    process = CEXAlertProcess(bot)
    process.tg_alert = Mock(return_value=([12345], []))
    alert = {
        "type": "s",
        "indicator": "PRICE",
        "comparison": "ABOVE",
        "target": 100,
        "trigger": {"cooldown_seconds": 60, "last_triggered": 0},
    }
    mock_config = Mock()
    mock_config.load_alerts.return_value = {"BTC/USDT": [alert]}
    mock_config.load_config.return_value = {"channels": ["12345"]}
    mocker.patch(
        "src.alert_processes.cex.LocalUserConfiguration", return_value=mock_config
    )
    mocker.patch(
        "src.alert_processes.cex.MongoDBUserConfiguration", return_value=mock_config
    )
    mocker.patch.object(
        process, "get_simple_indicator", return_value=(True, 110, "Triggered")
    )
    process.poll_user_alerts("12345")
    process.tg_alert.assert_called_once()
    assert alert["trigger"]["last_triggered"] > 0
    last_triggered_time = alert["trigger"]["last_triggered"]
    process.tg_alert.reset_mock()
    mocker.patch("time.time", return_value=last_triggered_time + 30)
    process.poll_user_alerts("12345")
    process.tg_alert.assert_not_called()
    mocker.patch("time.time", return_value=last_triggered_time + 65)
    process.poll_user_alerts("12345")
    process.tg_alert.assert_called_once()


def test_one_shot_alert_removal(mocker):
    bot = Mock()
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="dummy")
    process = CEXAlertProcess(bot)
    alert = {
        "type": "s",
        "indicator": "PRICE",
        "comparison": "ABOVE",
        "target": 100,
        "trigger": {"cooldown_seconds": None, "last_triggered": 0},
    }
    alerts_db = {"BTC/USDT": [alert]}
    mock_config = Mock()
    mock_config.load_alerts.return_value = alerts_db
    mock_config.load_config.return_value = {"channels": ["12345"]}
    mocker.patch(
        "src.alert_processes.cex.LocalUserConfiguration", return_value=mock_config
    )
    mocker.patch(
        "src.alert_processes.cex.MongoDBUserConfiguration", return_value=mock_config
    )
    mocker.patch.object(
        process, "get_simple_indicator", return_value=(True, 110, "Triggered")
    )
    process.tg_alert = Mock(return_value=([], ["12345"]))
    process.poll_user_alerts("12345")
    assert len(alerts_db["BTC/USDT"]) == 1
    process.tg_alert = Mock(return_value=(["12345"], []))
    process.poll_user_alerts("12345")
    assert "BTC/USDT" not in alerts_db or len(alerts_db["BTC/USDT"]) == 0


def test_worker_loops_continue_on_exception(mocker):
    bot = Mock()
    mocker.patch("src.alert_processes.cex.get_binance_price_url", return_value="dummy")
    process = CEXAlertProcess(bot)
    side_effect = [Exception("Transient error"), KeyboardInterrupt()]
    mocker.patch.object(process, "poll_all_alerts", side_effect=side_effect)
    mock_sleep = mocker.patch("time.sleep")
    process.run()
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(15)




def test_alert_cooldown_manager():
    manager = AlertCooldownManager(cooldown_seconds=300)

    # Initial trigger should pass
    assert manager.can_send_alert("XAUUSD_15M_BUY", current_time=1000.0) is True

    # Trigger within cooldown should fail
    assert manager.can_send_alert("XAUUSD_15M_BUY", current_time=1299.0) is False

    # Trigger after cooldown should pass
    assert manager.can_send_alert("XAUUSD_15M_BUY", current_time=1300.0) is True

    # Different key should pass regardless
    assert manager.can_send_alert("EURUSD_15M_SELL", current_time=1299.0) is True

    # Reset should clear the cooldown
    manager.reset("xauusd_15m_buy")
    assert manager.can_send_alert("XAUUSD_15M_BUY", current_time=1301.0) is True


def test_calculate_rsi_uptrend():
    closes = [
        10.0,
        11.0,
        12.0,
        13.0,
        14.0,
        15.0,
        16.0,
        17.0,
        18.0,
        19.0,
        20.0,
        21.0,
        22.0,
        23.0,
        24.0,
    ]
    # Pure uptrend should have avg_loss = 0, meaning RSI = 100.0
    assert calculate_rsi(closes, period=14) == 100.0


def test_calculate_rsi_downtrend():
    closes = [
        24.0,
        23.0,
        22.0,
        21.0,
        20.0,
        19.0,
        18.0,
        17.0,
        16.0,
        15.0,
        14.0,
        13.0,
        12.0,
        11.0,
        10.0,
    ]
    # Pure downtrend should have avg_gain = 0, meaning RSI = 0.0
    assert calculate_rsi(closes, period=14) == 0.0


def test_calculate_rsi_mixed():
    closes = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
    ]
    rsi = calculate_rsi(closes, period=14)
    # This should be approximately 70.46 based on Wilder's smoothing logic for this dataset
    assert 65.0 <= rsi <= 75.0


def test_calculate_rsi_invalid():
    closes = [10.0, 11.0]
    with pytest.raises(ValueError):
        calculate_rsi(closes, period=14)
