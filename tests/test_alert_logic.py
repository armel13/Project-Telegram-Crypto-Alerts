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
