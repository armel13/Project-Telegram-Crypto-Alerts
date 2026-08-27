import pytest, responses
from src.binance_client import fetch_binance_market_data
@responses.activate
def test_fetch_binance_market_data_valid(mocker):
    mocker.patch('src.utils.getenv', return_value='global')
    responses.add(responses.GET, "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT", json={"lastPrice": "50000.0", "priceChangePercent": "5.0"}, status=200)
    data = fetch_binance_market_data("BTC/USDT")
    assert data["lastPrice"] == "50000.0" and data["priceChangePercent"] == "5.0"
def test_verify_false_not_used(mocker):
    mocker.patch('src.utils.getenv', return_value='global')
    mock_get = mocker.patch('requests.get')
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"lastPrice": "50000.0", "priceChangePercent": "5.0"}
    mock_get.return_value = mock_response
    fetch_binance_market_data("BTC/USDT")
    mock_get.assert_called_once()
    kwargs = mock_get.call_args[1]
    assert "verify" not in kwargs or kwargs["verify"] is not False
@responses.activate
def test_fetch_binance_market_data_invalid_symbol(mocker):
    mocker.patch('src.utils.getenv', return_value='global')
    responses.add(responses.GET, "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=INVALID", json={"code": -1121, "msg": "Invalid symbol."}, status=400)
    with pytest.raises(ValueError, match="Invalid symbol"): fetch_binance_market_data("INVALID")
@responses.activate
def test_fetch_binance_market_data_html_response(mocker):
    mocker.patch('src.utils.getenv', return_value='global')
    responses.add(responses.GET, "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT", body="<html></html>", headers={"Content-Type": "text/html"}, status=200)
    with pytest.raises(ConnectionAbortedError): fetch_binance_market_data("BTC/USDT", retry_delay=0, maximum_retries=1)
@responses.activate
def test_fetch_binance_market_data_missing_fields(mocker):
    mocker.patch('src.utils.getenv', return_value='global')
    responses.add(responses.GET, "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT", json={"lastPrice": "50000.0"}, status=200)
    with pytest.raises(ValueError, match="Missing required fields"): fetch_binance_market_data("BTC/USDT")
