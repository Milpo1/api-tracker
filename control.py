# %%
import requests

# %%

# Set the base URL for the API
# base_url = 'http://35.232.150.192/'
base_url = 'http://localhost/'  # Uncomment this line to use localhost

# %%
# Example 1: Add a new ticker
url = base_url + 'api/tickers'
data = {
    "exchange": "gateio",
    "symbol": "BTC_USDT"
}
response = requests.post(url, json=data)
print("Add ticker response:", response.json())

# %%
# Example 2: Delete a ticker
url = base_url + 'api/tickers'
data = {
    "exchange": "gateio",
    "symbol": "BTC-USDT"
}
response = requests.delete(url, json=data)
print("Delete ticker response:", response.json())

# %%
# Example 3: Add a new calculated ticker
url = base_url + 'api/calculated_tickers'
data = {
    "name": "triasratio",
    "formula": "gateio_TRIAS_USDT / kucoin_TRIAS-USDT"
}
response = requests.post(url, json=data)
print("Add calculated ticker response:", response.json())

# %%
# Example 4: Delete a calculated ticker
url = base_url + 'api/calculated_tickers'
data = {
    "name": "TRIAS_RATIO",
    # "symbol": "BTC-USDT"
}
response = requests.delete(url, json=data)
print("Delete calculated ticker response:", response.json())

# %%
# Example 5: Add a new alert
url = base_url + 'api/alerts'
data = {
    "ticker": "Calculated_TriasRatio",
    "condition": "price < 0.98",
    "message": "{ticker} is < 0.98 current: {price}",
    "min_interval": 10
}
response = requests.post(url, json=data)
print("Add alert response:", response.json())

# %%
# Example 6: Delete an alert
url = base_url + 'api/alerts'
data = {
    "ticker": "calculated_triasratio",

    "condition": "price > 1.05"
}
response = requests.delete(url, json=data)
print("Delete alert response:", response.json())

# %%
# Example 7: Add a custom exchange
url = base_url + 'api/tickers'
data = {
    "exchange_name": "CustomExchange",
    "symbol": "CUSTOMSYMBOL",
    "websocket_url": "wss://custom.exchange.com/ws",
    "subscription_message": {"type": "subscribe", "symbol": "CUSTOMSYMBOL"},
    "price_extract_func": "lambda data: {'timestamp': int(time.time()), 'price': float(data['price'])}",
    "ping_message": {"type": "ping"}
}
response = requests.post(url, json=data)
print("Add custom exchange response:", response.json())
# %%
# Example 8: Enable alert, reset activation counter, change max activation count
url = base_url + 'api/alerts'
data = {
    "ticker": "Calculated_btc_Ratio",
    "condition": "price <= 1",
    "enabled": True,
    "reset": True,
    "max_activations": 5
}
response = requests.patch(url, json=data)
print("Add alert response:", response.json())
