import json
from unittest.mock import patch, Mock
from src.telegram import send_tradingview_signal_alert


@patch("requests.post")
def test_send_tradingview_signal_alert(mock_post):
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = {"ok": True}
    mock_post.return_value = mock_response

    # Prepare signal payload
    signal = {
        "symbol": "XAUUSD",
        "side": "BUY",
        "price": 2650.0,
        "timeframe": "1h",
        "strategy": "Gold Sniper",
        "stop_loss": 2645.0,
        "take_profit": 2660.0,
        "rsi": 45.0,
        "exchange": "FXCM",
    }

    # Call function
    result = send_tradingview_signal_alert("fake_token", "chat123", signal)

    # Assertions
    assert result == {"ok": True}

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botfake_token/sendMessage"
    assert kwargs["timeout"] == 10

    payload = kwargs["data"]
    assert payload["chat_id"] == "chat123"
    assert payload["parse_mode"] == "Markdown"

    text = payload["text"]
    assert "🟢 BUY XAUUSD" in text
    assert "[1h]" in text
    assert "*Strategy:* Gold Sniper" in text
    assert "*Entry Price:* `2650.0`" in text
    assert "*Stop Loss:* `2645.0`" in text
    assert "*Take Profit:* `2660.0`" in text
    assert "*RSI:* `45.0`" in text

    reply_markup = json.loads(payload["reply_markup"])
    inline_keyboard = reply_markup["inline_keyboard"]
    assert len(inline_keyboard) == 1
    assert len(inline_keyboard[0]) == 1
    assert inline_keyboard[0][0]["text"] == "📈 Open TradingView Chart"
    assert (
        inline_keyboard[0][0]["url"]
        == "https://www.tradingview.com/chart/?symbol=FXCM:XAUUSD"
    )


@patch("requests.post")
def test_send_tradingview_signal_alert_overbought_rsi(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {"ok": True}
    mock_post.return_value = mock_response

    signal = {"symbol": "BTCUSDT", "side": "SELL", "price": 65000.0, "rsi": 85.0}

    send_tradingview_signal_alert("fake_token", "chat123", signal)

    payload = mock_post.call_args[1]["data"]
    assert "🔴 SELL BTCUSDT" in payload["text"]
    assert "*RSI:* `85.0` (OVERBOUGHT)" in payload["text"]

    reply_markup = json.loads(payload["reply_markup"])
    assert (
        reply_markup["inline_keyboard"][0][0]["url"]
        == "https://www.tradingview.com/chart/?symbol=OANDA:BTCUSDT"
    )
