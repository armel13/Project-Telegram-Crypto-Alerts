import hmac
from typing import Any


def verify_webhook_secret(payload_secret: str | None, expected_secret: str) -> bool:
    if payload_secret is None:
        return False
    return hmac.compare_digest(payload_secret.encode(), expected_secret.encode())


def parse_tradingview_alert(payload: dict[str, Any]) -> dict[str, Any]:
    if "symbol" not in payload or "side" not in payload or "price" not in payload:
        raise ValueError("Missing required fields: symbol, side, or price")

    symbol = str(payload["symbol"]).upper()
    side = str(payload["side"]).upper()
    try:
        price = float(payload["price"])
    except ValueError:
        raise ValueError("Price must be a float")

    if side not in ("BUY", "SELL", "ALERT"):
        raise ValueError("Side must be BUY, SELL, or ALERT")

    if price <= 0:
        raise ValueError("Price must be > 0")

    default_exchange = (
        "BINANCE" if "USDT" in symbol or "BTC" in symbol or "ETH" in symbol else "OANDA"
    )

    return {
        "symbol": symbol,
        "side": side,
        "price": price,
        "timeframe": str(payload.get("timeframe", "15m")),
        "strategy": str(payload.get("strategy", "TradingView Alert")),
        "stop_loss": (
            float(payload["stop_loss"])
            if payload.get("stop_loss") is not None
            else None
        ),
        "take_profit": (
            float(payload["take_profit"])
            if payload.get("take_profit") is not None
            else None
        ),
        "rsi": float(payload["rsi"]) if payload.get("rsi") is not None else None,
        "exchange": str(payload.get("exchange", default_exchange)),
    }


def calculate_forex_gold_pip_risk(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    account_balance: float = 1000.0,
    risk_pct: float = 1.0,
) -> dict[str, float]:
    if entry_price <= 0 or stop_loss <= 0 or entry_price == stop_loss:
        raise ValueError("Invalid entry or stop loss price")

    risk_usd = account_balance * (risk_pct / 100.0)
    price_distance = abs(entry_price - stop_loss)

    symbol_upper = symbol.upper()
    if symbol_upper == "XAUUSD":
        # For XAUUSD, $1 price move = 10 pips = $100 for 1 standard lot (100 oz).
        # $100 * price_distance = risk for 1 standard lot
        reward_or_stop_pips = price_distance * 10.0
        risk_per_lot = price_distance * 100.0
    elif "JPY" in symbol_upper:
        # For JPY pairs, pip is usually the second decimal place (0.01)
        reward_or_stop_pips = price_distance * 100.0
        # Standard lot value for JPY varies, but simplifying to roughly $10 per pip for a standard lot:
        risk_per_lot = reward_or_stop_pips * 10.0
    else:
        # For standard Forex pairs (EURUSD, GBPUSD), pip is the fourth decimal place (0.0001)
        reward_or_stop_pips = price_distance * 10000.0
        # Standard lot (100k) risk is $10 per pip.
        risk_per_lot = reward_or_stop_pips * 10.0

    if risk_per_lot == 0:
        suggested_lot = 0.0
    else:
        suggested_lot = risk_usd / risk_per_lot

    return {
        "risk_usd": round(risk_usd, 2),
        "price_distance": round(price_distance, 5),
        "reward_or_stop_pips": round(reward_or_stop_pips, 2),
        "suggested_lot": round(suggested_lot, 2),
    }
