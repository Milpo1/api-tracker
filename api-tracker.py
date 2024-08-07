import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Any
import uuid

import requests
import websockets
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
import os

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_DISABLED = False
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHATID = os.getenv('TELEGRAM_CHATID')
if None in (TELEGRAM_TOKEN, TELEGRAM_CHATID):
    TELEGRAM_BOT_DISABLED = True
    
api_base_url = os.getenv('API_BASE_URL',' http://localhost/api')
    
# Flask app setup
app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///prices.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
with app.app_context():
    db.create_all()

def clean(input_data, chars_to_replace=',.!:-'):
    replace_with = '_'
    if isinstance(input_data, str):
        # Replace characters in the string
        for char in chars_to_replace:
            input_data = input_data.replace(char, replace_with).lower()
        return input_data
    elif isinstance(input_data, dict):
        # Create a new dictionary with modified keys
        new_dict = {}
        for key, value in input_data.items():
            new_key = key
            if isinstance(key, str):
                for char in chars_to_replace:
                    new_key = new_key.replace(char, replace_with).lower()
            new_dict[new_key] = value
        return new_dict
    else:
        # Return the input as is if it's neither a string nor a dictionary
        return input_data

# Price model
class Price(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exchange = db.Column(db.String(50), nullable=False)
    symbol = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

# Create database tables

class ExchangeWebSocket(ABC):
    def __init__(self, exchange_name: str, websocket_url: str):
        self.exchange_name = exchange_name
        self.websocket_url = websocket_url
        self.subscribed_symbols = set()
        self.price_updates = defaultdict(dict)
        self.logger = logging.getLogger(f"{exchange_name}Exchange")
        self.websocket = None
        self.last_ping_time = 0

    @abstractmethod
    async def subscribe(self, symbols: List[str]):
        pass

    @abstractmethod
    async def on_message(self, message: str):
        pass

    async def connect(self):
        while True:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    self.websocket = websocket
                    self.logger.info(f"Connected to {self.exchange_name} WebSocket")
                    if self.subscribed_symbols:
                        await self.subscribe(list(self.subscribed_symbols))
                    
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=30)
                            await self.on_message(message)
                            
                            # Send ping every 20 seconds
                            current_time = time.time()
                            if current_time - self.last_ping_time > 20:
                                await self.ping()
                                self.last_ping_time = current_time
                                
                        except asyncio.TimeoutError:
                            await self.ping()
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.error(f"WebSocket connection closed: {e}")
                self.logger.info("Attempting to reconnect in 5 seconds...")
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}")
                self.logger.info("Attempting to reconnect in 5 seconds...")
                await asyncio.sleep(5)

    async def ping(self):
        try:
            ping_message = self.get_ping_message()
            await self.websocket.send(json.dumps(ping_message))
            self.logger.info(f"Sent ping to {self.exchange_name} WebSocket")
        except Exception as e:
            self.logger.error(f"Error sending ping to {self.exchange_name} WebSocket: {e}")

    def get_ping_message(self):
        # Default ping message, can be overridden in subclasses if needed
        return {
            "id": int(time.time() * 1000),
            "type": "ping"
        }
        
    def add_symbol(self, symbol: str):
        self.subscribed_symbols.add(symbol)

    def remove_symbol(self, symbol: str):
        self.subscribed_symbols.remove(symbol)

class KuCoinWebSocket(ExchangeWebSocket):
    def __init__(self):
        BASE_URL = 'https://api.kucoin.com'
        connect_id = str(uuid.uuid4())
        response = requests.post(f'{BASE_URL}/api/v1/bullet-public')
        response = response.json()
        TOKEN = response['data']['token']
        KUCOIN_WEBSOCKET_URL = response['data']['instanceServers'][0]['endpoint'] + '?token=' + TOKEN + f'&[connectId={connect_id}]'

        super().__init__("KuCoin", KUCOIN_WEBSOCKET_URL)  # Note: You'll need to implement the token-based connection for KuCoin

    async def subscribe(self, symbols: List[str]):
        subscription_message = {
            "id": int(time.time() * 1000),
            "type": "subscribe",
            "topic": f"/market/ticker:{','.join(symbols)}",
            "privateChannel": False,
            "response": True
        }
        await self.websocket.send(json.dumps(subscription_message))

    async def on_message(self, message: str):
        data = json.loads(message)
        if 'data' in data and 'price' in data['data']:
            symbol = data['topic'].split(':')[1]
            self.price_updates[symbol] = {
                'timestamp': int(time.time()),
                'price': float(data['data']['price'])
            }

class GateioWebSocket(ExchangeWebSocket):
    def __init__(self):
        super().__init__("GateIO", "wss://api.gateio.ws/ws/v4/")

    async def subscribe(self, symbols: List[str]):
        subscription_message={
            "time": int(time.time()),
            "channel": "spot.tickers",
            "event": "subscribe",
            "payload": symbols
        }
        await self.websocket.send(json.dumps(subscription_message))

    async def on_message(self, message: str):
        data = json.loads(message)
        if 'result' in data and type(data['result']) is dict and 'last' in data['result'] and 'currency_pair' in data['result']:
            symbol = data['result']['currency_pair']
            self.price_updates[symbol] = {
                'timestamp': int(time.time()),
                'price': float(data['result']['last'])
            }
    
    def get_ping_message(self):
        return {
            "time": int(time.time() * 1000),
            "channel": "spot.ping"
        }
            
class MexcWebSocket(ExchangeWebSocket):
    def __init__(self):
        super().__init__("MEXC", "wss://wbs.mexc.com/ws")

    async def subscribe(self, symbols: List[str]):
        subscription_message = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.miniTicker.v3.api@{symbol}@UTC+2" for symbol in symbols]
        }
        await self.websocket.send(json.dumps(subscription_message))

    async def on_message(self, message: str):
        data = json.loads(message)
        if 'c' in data and 'spot@public.miniTicker' in data['c'] and 'd' in data and 'p' in data['d']:
            symbol = data['c'].split('@')[-2]
            self.price_updates[symbol] = {
                'timestamp': int(time.time()),
                'price': float(data['d']['p'])
            }
            
    def get_ping_message(self):
        return {
            # "time": int(time.time() * 1000),
            "method": "PING"
        }

class CalculatedTicker:
    def __init__(self, name: str, formula: str):
        self.name = name
        self.formula = clean(formula)
        self.price = None
        self.timestamp = None
        self.last_recorded_price = None

    def update_price(self, ticker_manager):
        try:
            prices = ticker_manager.get_current_prices()
            prices = clean(prices)
            price = eval(self.formula, {}, prices)
            if price != self.price:
                self.price = price
                self.timestamp = int(time.time())
                return True
            return False
        except Exception as e:
            logging.error(f"Error calculating price for {self.name}: {e}")
            return False

class TickerManager:
    def __init__(self, telegram_bot_token):
        self.exchanges = {
            "kucoin": KuCoinWebSocket(),
            "mexc": MexcWebSocket(),
            "gateio" : GateioWebSocket()
        }
        self.logger = logging.getLogger("TickerManager")
        self.last_recorded_prices = defaultdict(lambda: defaultdict(float))
        self.calculated_tickers = {}
        self.alert_manager = AlertManager(telegram_bot_token)

        
    def add_ticker(self, exchange: str, symbol: str):
        exchange = exchange.lower()
        if exchange in self.exchanges:
            exchange_ws = self.exchanges[exchange]
            exchange_ws.add_symbol(symbol)
            
            # Create a new thread to run the subscription
            thread = threading.Thread(target=self._run_subscription, args=(exchange_ws, symbol))
            thread.start()
            
            self.logger.info(f"Added ticker and started subscription thread: {exchange} for symbol {symbol}")
        else:
            raise ValueError(f"Unknown exchange: {exchange}")

    def _run_subscription(self, exchange_ws, symbol):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._subscribe_to_symbol(exchange_ws, symbol))
        finally:
            loop.close()

    async def _subscribe_to_symbol(self, exchange_ws, symbol):
        if exchange_ws.websocket:
            await exchange_ws.subscribe([symbol])
        else:
            self.logger.warning(f"WebSocket not connected for {exchange_ws.exchange_name}. Will subscribe when connected.")

            
    def remove_ticker(self, exchange: str, symbol: str):
        if exchange.lower() in self.exchanges:
            self.exchanges[exchange.lower()].remove_symbol(symbol)
            self.logger.info(f"Removed ticker: {exchange} for symbol {symbol}")
        else:
            raise ValueError(f"Unknown exchange: {exchange}")

    async def start_all(self):
        await asyncio.gather(*[exchange.connect() for exchange in self.exchanges.values()])

    def add_calculated_ticker(self, name: str, formula: str):
        self.calculated_tickers[name] = CalculatedTicker(name, formula)
        self.logger.info(f"Added calculated ticker: {name} with formula: {formula}")

    def remove_calculated_ticker(self, name: str):
        if name in self.calculated_tickers:
            del self.calculated_tickers[name]
            self.logger.info(f"Removed calculated ticker: {name}")
        else:
            raise ValueError(f"Unknown calculated ticker: {name}")

    def get_current_prices(self, timestamps = False):
        prices = {}
        for exchange_name, exchange in self.exchanges.items():
            for symbol, price_data in exchange.price_updates.items():
                prices[f"{exchange_name}_{symbol}"] = price_data if timestamps else price_data['price']
                
        for name, ticker in self.calculated_tickers.items():
            if ticker.price is not None and ticker.timestamp is not None:
                prices[f"Calculated_{name}"] = {
                    "price": ticker.price,     
                } 
                
                if timestamps:
                    prices[f"Calculated_{name}"]["timestamp"] = ticker.timestamp
        return prices

    async def update_calculated_tickers(self):
        while True:
            await asyncio.sleep(1)  # Update calculated tickers every second
            for ticker in self.calculated_tickers.values():
                ticker.update_price(self)

    async def append_to_database(self):
        while True:
            await asyncio.sleep(1)
            with app.app_context():
                for _, exchange in self.exchanges.items():
                    exchange_name = exchange.exchange_name
                    for symbol, price_data in exchange.price_updates.items():
                        current_price = price_data['price']
                        last_price = self.last_recorded_prices[exchange_name][symbol]
                        
                        if current_price != last_price:
                            price_entry = Price(
                                exchange=exchange_name,
                                symbol=symbol,
                                timestamp=price_data['timestamp'],
                                price=current_price
                            )
                            db.session.add(price_entry)
                            self.logger.info(f"Price update: {exchange_name} : {symbol} : {current_price}")
                            self.last_recorded_prices[exchange_name][symbol] = current_price
                
                # Add calculated tickers to the database
                for name, ticker in self.calculated_tickers.items():
                    if ticker.price is not None and ticker.timestamp is not None:
                        if ticker.price != ticker.last_recorded_price:
                            price_entry = Price(
                                exchange="Calculated",
                                symbol=name,
                                timestamp=ticker.timestamp,
                                price=ticker.price
                            )
                            db.session.add(price_entry)
                            self.logger.info(f"Calculated price update: {name} : {ticker.price:.5f}")
                            ticker.last_recorded_price = ticker.price
                
                db.session.commit()

    def get_all_tickers(self):
        tickers = {exchange_name: list(exchange.subscribed_symbols) for exchange_name, exchange in self.exchanges.items()}
        tickers["Calculated"] = list(self.calculated_tickers.keys())
        return tickers
    
    def add_alert(self, ticker, condition, message, min_interval, max_activations=None):
        self.alert_manager.add_alert(ticker, condition, message, min_interval, max_activations)

    def enable_alert(self, ticker, condition):
        return self.alert_manager.enable_alert(ticker, condition)

    def disable_alert(self, ticker, condition):
        return self.alert_manager.disable_alert(ticker, condition)

class Alert:
    def __init__(self, ticker, condition, message, min_interval, max_activations=None):
        self.ticker = clean(ticker)
        self.condition = condition
        self.message = message
        self.min_interval = min_interval
        self.last_triggered = 0
        self.max_activations = max_activations
        self.activation_count = 0
        self.enabled = True

    def can_trigger(self):
        if not self.enabled:
            return False
        if self.max_activations is not None and self.activation_count >= self.max_activations:
            self.enabled = False
            return False
        return True

    def trigger(self):
        self.activation_count += 1
        self.last_triggered = int(time.time())

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

class AlertManager:
    def __init__(self, telegram_bot_token):
        self.alerts = []
        self.bot = Bot(token=telegram_bot_token)
        self.chat_id = TELEGRAM_CHATID

    def add_alert(self, ticker, condition, message, min_interval, max_activations=None):
        self.alerts.append(Alert(ticker, condition, message, min_interval, max_activations))

    def enable_alert(self, ticker, condition, reset=False, new_max_activations = None):
        ticker = ticker.lower()
        for alert in self.alerts:
            if alert.ticker == ticker and alert.condition == condition:
                if new_max_activations is not None:
                    alert.max_activations = new_max_activations
                if reset:
                    alert.activation_count = 0
                alert.enable()
                return True
        return False

    def disable_alert(self, ticker, condition):
        ticker = ticker.lower()
        for alert in self.alerts:
            if alert.ticker == ticker and alert.condition == condition:
                alert.disable()
                return True
        return False

    async def check_alerts(self, ticker_manager):
        while True:
            current_time = int(time.time())
            prices = ticker_manager.get_current_prices()
            prices = clean(prices)
            for alert in self.alerts:
                if alert.ticker in prices:
                    price = prices[alert.ticker]
                    if eval(alert.condition, {}, price) and alert.can_trigger():
                        if current_time - alert.last_triggered >= alert.min_interval:
                            await self.send_notification(alert, price['price'])
                            alert.trigger()
            
            # Remove alerts that have reached their max activations (dont actually)
            # self.alerts = [alert for alert in self.alerts if alert.can_trigger() or not alert.enabled]
            
            await asyncio.sleep(1)  # Check alerts every second

    async def send_notification(self, alert, price):
        if self.chat_id is None:
            logging.error("Telegram chat ID is not set")
            return

        try:
            info=''
            message = alert.message.format(ticker=alert.ticker, price=price)
            if not TELEGRAM_BOT_DISABLED:
                await self.bot.send_message(chat_id=self.chat_id, text=message)
                
            else:
                info = ', bot disabled'
            logging.info(f"Sent alert{info}: {message}")
        except TelegramError as e:
            logging.error(f"Failed to send Telegram message: {e}")

# Initialize the TickerManager
ticker_manager = TickerManager(TELEGRAM_TOKEN)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

@app.route('/api/prices', methods=['GET'])
@limiter.limit("30 per minute")
def get_prices():
    end_time = int(time.time())
    start_time = end_time - 120  # Last 2 minutes
    
    with app.app_context():
        result = {}
        for _, exchange in ticker_manager.exchanges.items():
            exchange_name = exchange.exchange_name
            for symbol in exchange.subscribed_symbols:
                prices = Price.query.filter_by(exchange=exchange_name, symbol=symbol)\
                    .filter(Price.timestamp >= start_time)\
                    .order_by(Price.timestamp.desc())\
                    .limit(120)\
                    .all()
                
                if not prices:
                    prices = [{'price': 0, 'timestamp': end_time}] * 120
                else:
                    prices.reverse()

                result[f"{exchange_name}_{symbol}"] = [{"price": price.price, "timestamp": price.timestamp} for price in prices]
        
        # Add calculated tickers
        for name in ticker_manager.calculated_tickers.keys():
            prices = Price.query.filter_by(exchange="Calculated", symbol=name)\
                .filter(Price.timestamp >= start_time)\
                .order_by(Price.timestamp.desc())\
                .limit(120)\
                .all()
            
            if not prices:
                prices = [{'price': 0, 'timestamp': end_time}] * 120
            else:
                prices.reverse()

            result[f"Calculated_{name}"] = [{"price": price.price, "timestamp": price.timestamp} for price in prices]
    
    return jsonify(result)

@app.route('/api/current_price', methods=['GET'])
@limiter.limit("100 per minute")
def get_price():
    result = ticker_manager.get_current_prices(timestamps=True)
    return jsonify(result)

@app.route('/api/tickers', methods=['GET', 'POST', 'DELETE'])
@limiter.limit("10 per minute")
def manage_tickers():
    if request.method == 'GET':
        return jsonify(ticker_manager.get_all_tickers())
    
    elif request.method == 'POST':
        data = request.json
        if 'exchange' in data and 'symbol' in data:
            try:
                ticker_manager.add_ticker(data['exchange'], data['symbol'])
                return jsonify({"message": f"Ticker {data['exchange']}_{data['symbol']} added successfully"}), 201
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            return jsonify({"error": "Invalid request data"}), 400
    
    elif request.method == 'DELETE':
        data = request.json
        if 'exchange' in data and 'symbol' in data:
            try:
                ticker_manager.remove_ticker(data['exchange'], data['symbol'])
                return jsonify({"message": f"Ticker {data['exchange']}_{data['symbol']} removed successfully"}), 200
            except ValueError as e:
                return jsonify({"error": str(e)}), 404
        else:
            return jsonify({"error": "Invalid request data"}), 400

@app.route('/api/calculated_tickers', methods=['GET', 'POST', 'DELETE'])
@limiter.limit("10 per minute")
def manage_calculated_tickers():
    if request.method == 'GET':
        return jsonify({name: ticker.formula for name, ticker in ticker_manager.calculated_tickers.items()})
    
    elif request.method == 'POST':
        data = request.json
        if 'name' in data and 'formula' in data:
            try:
                ticker_manager.add_calculated_ticker(data['name'], data['formula'])
                return jsonify({"message": f"Calculated ticker {data['name']} added successfully"}), 201
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            return jsonify({"error": "Invalid request data"}), 400
    
    elif request.method == 'DELETE':
        data = request.json
        if 'name' in data:
            try:
                ticker_manager.remove_calculated_ticker(data['name'])
                return jsonify({"message": f"Calculated ticker {data['name']} removed successfully"}), 200
            except ValueError as e:
                return jsonify({"error": str(e)}), 404
        else:
            return jsonify({"error": "Invalid request data"}), 400

@app.route('/api/alerts', methods=['GET', 'POST', 'DELETE', 'PATCH'])
@limiter.limit("10 per minute")
def manage_alerts():
    if request.method == 'GET':
        alerts = [
            {
                "ticker": alert.ticker,
                "condition": alert.condition,
                "message": alert.message,
                "min_interval": alert.min_interval,
                "max_activations": alert.max_activations,
                "activation_count": alert.activation_count,
                "last_triggered": alert.last_triggered,
                "enabled": alert.enabled
            }
            for alert in ticker_manager.alert_manager.alerts
        ]
        return jsonify(alerts)
    
    elif request.method == 'POST':
        data = request.json
        required_fields = ['ticker', 'condition', 'message', 'min_interval']
        if all(field in data for field in required_fields):
            try:
                ticker = data['ticker']
                max_activations = data.get('max_activations')
                
                ticker_manager.add_alert(
                    ticker,
                    data['condition'],
                    data['message'],
                    int(data['min_interval']),
                    max_activations
                )
                return jsonify({"message": f"Alert for {ticker} added successfully"}), 201
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            return jsonify({"error": "Invalid request data"}), 400
    
    elif request.method == 'DELETE':
        data = request.json
        if 'ticker' in data and 'condition' in data:
            alerts = ticker_manager.alert_manager.alerts
            for i, alert in enumerate(alerts):
                if alert.ticker == data['ticker'] and alert.condition == data['condition']:
                    del alerts[i]
                    return jsonify({"message": f"Alert for {data['ticker']} removed successfully"}), 200
            return jsonify({"error": "Alert not found"}), 404
        else:
            return jsonify({"error": "Invalid request data"}), 400

    elif request.method == 'PATCH':
        data = request.json
        if 'ticker' in data and 'condition' in data and 'enabled' in data:
            if data['enabled']:
                max_activations = data.get('max_activations')
                reset = data.get('reset',False)
                    
                success = ticker_manager.alert_manager.enable_alert(data['ticker'], data['condition'], reset, max_activations)
            else:
                success = ticker_manager.alert_manager.disable_alert(data['ticker'], data['condition'])
            
            if success:
                status = "enabled" if data['enabled'] else "disabled"
                return jsonify({"message": f"Alert for {data['ticker']} {status} successfully"}), 200
            else:
                return jsonify({"error": "Alert not found"}), 404
        else:
            return jsonify({"error": "Invalid request data"}), 400

@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')
@app.route('/config.json')
def serve_config():
    return send_from_directory('.', 'config.json')

async def start_background_tasks():
    # Start WebSocket connections and database append coroutine
    await asyncio.gather(
        ticker_manager.start_all(),
        ticker_manager.append_to_database(),
        ticker_manager.update_calculated_tickers()
    )

def run_flask():
    print("Starting Flask application...")
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=80)

async def main():
    # Add initial tickers
    ticker_manager.add_ticker("mexc", "BTCUSDT")
    # ticker_manager.add_ticker("mexc", "ETHUSDT")
    ticker_manager.add_ticker("kucoin", "BTC-USDT")

    # Add calc tikcers alerts
    ticker_manager.add_calculated_ticker("BTC_RATIO", "mexc_BTCUSDT / kucoin_BTC-USDT")
    # ticker_manager.add_alert("Calculated_BTC_RATIO", "price >= 1", "🚀 {ticker}  is above 1.01. Current: ${price:.4f}", 10)
    # ticker_manager.add_alert("Calculated_BTC_RATIO", "price <= 1", "🚀 {ticker}  is below 0.99. Current: ${price:.4f}", 10, 3)

    # ticker_manager.disable_alert("Calculated_BTC_RATIO", "price >= 1")

    # Start background tasks
    background_task = asyncio.create_task(start_background_tasks())
    alert_task = asyncio.create_task(ticker_manager.alert_manager.check_alerts(ticker_manager))

    # Run Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Wait for background tasks to complete (which they never will in this case)
    await asyncio.gather(background_task, alert_task)

if __name__ == '__main__':
    asyncio.run(main())
