import pytest
from src.tradingview_webhook import (
    verify_webhook_secret,
    parse_tradingview_alert,
    calculate_forex_gold_pip_risk,
)


def test_verify_webhook_secret():
    assert verify_webhook_secret("my_secret", "my_secret") is True
    assert verify_webhook_secret("wrong_secret", "my_secret") is False
    assert verify_webhook_secret(None, "my_secret") is False


def test_parse_tradingview_alert_valid_xauusd():
    payload = {
        "symbol": "XAUUSD",
        "side": "BUY",
        "price": "2650.0",
        "timeframe": "1h",
        "strategy": "Gold Sniper",
        "stop_loss": 2645.0,
        "take_profit": 2660.0,
        "rsi": 45.0,
        "exchange": "FXCM",
    }
    parsed = parse_tradingview_alert(payload)
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["side"] == "BUY"
    assert parsed["price"] == 2650.0
    assert parsed["timeframe"] == "1h"
    assert parsed["strategy"] == "Gold Sniper"
    assert parsed["stop_loss"] == 2645.0
    assert parsed["take_profit"] == 2660.0
    assert parsed["rsi"] == 45.0
    assert parsed["exchange"] == "FXCM"


def test_parse_tradingview_alert_valid_eurusd_defaults():
    payload = {
        "symbol": "EURUSD",
        "side": "sell",
        "price": 1.0500,
    }
    parsed = parse_tradingview_alert(payload)
    assert parsed["symbol"] == "EURUSD"
    assert parsed["side"] == "SELL"
    assert parsed["price"] == 1.0500
    assert parsed["timeframe"] == "15m"
    assert parsed["strategy"] == "TradingView Alert"
    assert parsed["stop_loss"] is None
    assert parsed["take_profit"] is None
    assert parsed["rsi"] is None
    assert parsed["exchange"] == "OANDA"


def test_parse_tradingview_alert_valid_crypto_default_exchange():
    payload = {
        "symbol": "BTCUSDT",
        "side": "ALERT",
        "price": 65000.0,
    }
    parsed = parse_tradingview_alert(payload)
    assert parsed["exchange"] == "BINANCE"


def test_parse_tradingview_alert_invalid_missing_fields():
    with pytest.raises(ValueError):
        parse_tradingview_alert({"symbol": "BTCUSDT", "side": "BUY"})


def test_parse_tradingview_alert_invalid_price():
    with pytest.raises(ValueError):
        parse_tradingview_alert({"symbol": "BTCUSDT", "side": "BUY", "price": -100})
    with pytest.raises(ValueError):
        parse_tradingview_alert(
            {"symbol": "BTCUSDT", "side": "BUY", "price": "invalid"}
        )


def test_parse_tradingview_alert_invalid_side():
    with pytest.raises(ValueError):
        parse_tradingview_alert({"symbol": "BTCUSDT", "side": "HOLD", "price": 65000.0})


def test_calculate_forex_gold_pip_risk_xauusd():
    result = calculate_forex_gold_pip_risk("XAUUSD", 2650.0, 2645.0)
    # price distance = 5.0
    # reward or stop pips = 5.0 * 10 = 50.0
    # risk per lot = 5.0 * 100 = 500.0
    # risk usd (1% of 1000) = 10.0
    # suggested lot = 10.0 / 500.0 = 0.02
    assert result["risk_usd"] == 10.0
    assert result["price_distance"] == 5.0
    assert result["reward_or_stop_pips"] == 50.0
    assert result["suggested_lot"] == 0.02


def test_calculate_forex_gold_pip_risk_eurusd():
    result = calculate_forex_gold_pip_risk("EURUSD", 1.0500, 1.0450)
    # distance = 0.0050
    # reward or stop pips = 0.0050 * 10000 = 50.0
    # risk per lot = 50.0 * 10 = 500.0
    # risk usd = 10.0
    # suggested lot = 10.0 / 500.0 = 0.02
    assert result["risk_usd"] == 10.0
    assert result["price_distance"] == 0.0050
    assert result["reward_or_stop_pips"] == 50.0
    assert result["suggested_lot"] == 0.02


def test_calculate_forex_gold_pip_risk_jpy():
    result = calculate_forex_gold_pip_risk("USDJPY", 150.50, 150.00)
    # distance = 0.50
    # reward or stop pips = 0.50 * 100 = 50.0
    # risk per lot = 50.0 * 10 = 500.0
    assert result["risk_usd"] == 10.0
    assert result["price_distance"] == 0.50
    assert result["reward_or_stop_pips"] == 50.0
    assert result["suggested_lot"] == 0.02


def test_calculate_forex_gold_pip_risk_invalid():
    with pytest.raises(ValueError):
        calculate_forex_gold_pip_risk("XAUUSD", 2650.0, 2650.0)
    with pytest.raises(ValueError):
        calculate_forex_gold_pip_risk("XAUUSD", -2650.0, 2645.0)
