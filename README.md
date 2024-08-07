
# API-Tracker: Faster than TradingView ;)

This application is a real-time price tracker that fetches and displays price data from multiple exchanges. It includes a backend server built with Flask and a frontend web interface.
 
The prices refresh on a **1-second interval** basis. 

You can create calculated tickers based on existing ones.

You can set up **alerts** that send you an **instant notification** through Telegram.

## Features
- Real-time price updates from multiple exchanges (current built-ins are KuCoin, MEXC, Gate.io)
- Custom calculated tickers
- Price alerts with Telegram notifications
- Historical price charts
- RESTful API for managing tickers and alerts
- Support for adding custom exchanges

## Installation

1. Clone the repository
2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```
3. Set up your environment variables in a `.env` file:
   ```
   TELEGRAM_TOKEN=your_telegram_bot_token
   TELEGRAM_CHATID=your_telegram_chat_id
   ```
   Replace `your_telegram_bot_token` and `your_telegram_chat_id` with your actual Telegram bot token and chat ID.

## Usage

1. You have two options to run the application:

   a. Run directly with Python:
      ```
      python api-tracker.py
      ```

   b. Use Docker:
      - Make sure you have Docker installed on your system.
      - Build the Docker image:
        ```
        docker build -t api-tracker .
        ```
      - Run the Docker container:
        ```
        docker run -p 80:80 --env-file .env api-tracker
        ```
      This will start the container, mapping port 80 of the container to port 80 on your host machine, and using the environment variables from your `.env` file.

2. Open `localhost` in a web browser to view the frontend interface.



## Built-in Exchanges

The application comes with built-in support for the following exchanges:

1. KuCoin
2. MEXC
3. Gate.io

These exchanges are pre-configured and ready to use out of the box. However, you can connect to any API you'd like (see the Custom Exchange Connections section at the bottom)

## API Endpoints

### Get Current Prices

```
GET /api/current_price
```

Example response:
```json
{
  "kucoin_BTC-USDT": {
    "price": 50123.45,
    "timestamp": 1628097600
  },
  "mexc_BTCUSDT": {
    "price": 50125.67,
    "timestamp": 1628097601
  }
}
```

### Manage Tickers

 - Get all tickers:

```
GET /api/tickers
```

 - Add a new ticker:

```
POST /api/tickers
Content-Type: application/json

{
  "exchange": "kucoin",
  "symbol": "BTC-USDT"
}
```

 - Remove a ticker:

```
DELETE /api/tickers
Content-Type: application/json

{
  "exchange": "kucoin",
  "symbol": "BTC-USDT"
}
```

### Manage Calculated Tickers

 - Get all calculated tickers:

```
GET /api/calculated_tickers
```

 - Add a new calculated ticker:

```
POST /api/calculated_tickers
Content-Type: application/json

{
  "name": "BTC_RATIO",
  "formula": "kucoin_BTC-USDT / mexc_BTCUSDT"
}
```

 - Remove a calculated ticker:

```
DELETE /api/calculated_tickers
Content-Type: application/json

{
  "name": "BTC_RATIO"
}
```

### Manage Alerts

 - Get all alerts:

```
GET /api/alerts
```

 - Add a new alert:

```
POST /api/alerts
Content-Type: application/json

{
  "ticker": "kucoin_BTC-USDT",
  "condition": "price > 50000",
  "message": "{ticker} is above $50,000! Current: ${price:.4f}", 
			# custom alert message. use {ticker} and {price} for auto-fill
  "min_interval": 3600
		    # minimum interval beetween alert trigger in seconds
  "max_activations": 5
			# (optional, def: None) maximum number of activation
}
```

 - Remove an alert:

```
DELETE /api/alerts
Content-Type: application/json

{
  "ticker": "kucoin_BTC-USDT",
  "condition": "price > 50000"
}
```
 - Patch an alert:
```
PATCH /api/alerts
Content-Type: application/json
{
  "ticker": "Calculated_btc_Ratio",
  "condition": "price <= 1",
  "enabled": True, 					# enabled flag
  "reset": True, 					# (optional, def: False) reset activation count
  "max_activations": 5 				# (optional) set max activation count
}
```
### Custom Exchange Connections

You can extend the application to support additional exchanges by adding custom exchange connections. To add a custom exchange, you need to provide the following information:

- Exchange name
- WebSocket URL
- Subscription message format
- Price extraction function
- Ping message (if required by the exchange)

To add a custom exchange, use the following API endpoint:

```
POST /api/tickers
Content-Type: application/json

{
  "exchange_name": "CustomExchange",
  "symbol": "BTCUSDT",
  "websocket_url": "wss://stream.customexchange.com/ws",
  "subscription_message": {"type": "subscribe", "symbol": "BTCUSDT"},
  "price_extract_func": "lambda data: {'timestamp': int(time.time()), 'price': float(data['lastPrice'])}",
  "ping_message": {"type": "ping"}
}
```

The `price_extract_func` should be a Python lambda function that takes the WebSocket message as input and returns a dictionary with 'timestamp' and 'price' keys.

Note: The custom exchange feature requires careful implementation  to ensure proper handling of different WebSocket protocols and <u>message formats</u>.
