from collections.abc import Iterator

from .config import PLANS


def get_effective_plan(config: dict) -> str:
    """Return the effective plan, treating expired plans as free."""
    from datetime import datetime, timezone

    plan = str(config.get("plan", "free")).lower()
    expiration_str = config.get("plan_expiration")

    if plan == "free" or not expiration_str:
        return plan

    try:
        # Parse timezone-aware datetime or fallback to assuming UTC for naive timestamps
        expiration = datetime.fromisoformat(expiration_str)
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
    except ValueError:
        return "free"  # Treat invalid as expired/free

    now = datetime.now(timezone.utc)

    if now >= expiration:
        return "free"
    return plan


def get_effective_alert_limit(config: dict) -> int:
    """Return a safe alert limit for a stored user configuration."""
    plan = get_effective_plan(config)
    return PLANS.get(plan, PLANS["free"])


def iter_eligible_alerts(
    alerts_database: dict, limit: int
) -> Iterator[tuple[str, int, dict]]:
    """Yield the first alerts that fit the plan, preserving stored JSON order."""
    emitted = 0
    for pair, alerts in alerts_database.items():
        for index, alert in enumerate(alerts):
            if emitted >= limit:
                return
            yield pair, index, alert
            emitted += 1
