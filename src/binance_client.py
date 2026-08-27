import requests
import json
from .utils import get_binance_price_url


def fetch_binance_market_data(
    token_pair: str, timeout: int = 10, retry_delay: int = 2, maximum_retries: int = 5
) -> dict:
    url = get_binance_price_url().format(token_pair.replace("/", "").upper())
    for attempt in range(1, maximum_retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 451:
                raise ConnectionError(
                    f"HTTP 451: Binance is unavailable in this region (url: {url})."
                )
            if "text/html" in response.headers.get("Content-Type", ""):
                raise ConnectionError(
                    f"Received HTML response instead of JSON from Binance (url: {url})."
                )
            try:
                data = response.json()
            except ValueError:
                raise ConnectionError(
                    f"Failed to parse JSON response from Binance (url: {url})."
                )
            if not isinstance(data, dict):
                raise ValueError(
                    f"Unexpected JSON format from Binance: expected dict, got {type(data).__name__}"
                )
            if "code" in data and "msg" in data:
                if response.status_code >= 400 and response.status_code < 500:
                    raise ValueError(
                        f"Binance API Error (Code: {data['code']}): {data['msg']} (url: {url})"
                    )
                else:
                    raise ConnectionError(
                        f"Binance API Server Error (Code: {data['code']}): {data['msg']}"
                    )
            response.raise_for_status()
            if "lastPrice" not in data or "priceChangePercent" not in data:
                raise ValueError(
                    f"Missing required fields 'lastPrice' or 'priceChangePercent' in Binance response: {data}"
                )
            return data
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            ConnectionError,
        ) as e:
            if attempt == maximum_retries:
                raise ConnectionAbortedError(
                    f"Binance request ({url}) failed after {attempt} retries. Last error: {str(e)}"
                )
            import time

            time.sleep(retry_delay)
    raise ConnectionAbortedError(f"Binance request ({url}) failed.")
