import time


class AlertCooldownManager:
    def __init__(self, cooldown_seconds: int = 300) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.last_triggered: dict[str, float] = {}

    def can_send_alert(self, key: str, current_time: float | None = None) -> bool:
        normalized_key = key.upper()
        if current_time is None:
            current_time = time.time()

        last_time = self.last_triggered.get(normalized_key, 0.0)
        if current_time - last_time >= self.cooldown_seconds:
            self.last_triggered[normalized_key] = current_time
            return True
        return False

    def reset(self, key: str) -> None:
        normalized_key = key.upper()
        if normalized_key in self.last_triggered:
            del self.last_triggered[normalized_key]


def calculate_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        raise ValueError(
            f"Not enough data to calculate RSI. Needs at least {period + 1} periods."
        )

    gains = []
    losses = []

    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0.0:
        return 100.0

    # Smoothed Moving Average (Wilder's Smoothing)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gain = diff
            loss = 0.0
        else:
            gain = 0.0
            loss = abs(diff)

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0.0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)
