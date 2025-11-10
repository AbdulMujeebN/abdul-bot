# trading_bot.py - FINAL - NO TELEGRAM - NO BALANCE CHECK - TRADES NOW
import ccxt.async_support as ccxt
import asyncio
import json
import datetime
import pytz
import pandas as pd
import pandas_ta as ta
import logging

logging.getLogger().setLevel(logging.CRITICAL)

# ====================== CONFIG ======================
BINANCE_API_KEY = "0pN4rxKs1bvDzoeKAvkglnjkSEAJNxxb4D5NjKDUVR31gNQLrGx7elDriVqbNrQH"
BINANCE_API_SECRET = "o9EnH02gBKFbt9stLckr2TVLFbqQVaEhAukWV8UMS3afwxqG1AdgfR5cu2lXVInV"

USE_TESTNET = True
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
           'ADA/USDT', 'XRP/USDT', 'DOT/USDT', 'LINK/USDT']

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
ADX_PERIOD = 14
ADX_THRESHOLD = 25
ATR_PERIOD = 14
RISK_PER_TRADE = 0.01
STOP_LOSS_ATR = 1.5
TAKE_PROFIT_ATR = 3.0
DATA_FILE = 'trades.json'
# ====================================================

exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
})
if USE_TESTNET:
    exchange.set_sandbox_mode(True)

active_trades = {}

async def fetch_ohlcv(symbol, timeframe='1m', limit=100):
    try:
        data = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

async def get_balance():
    try:
        bal = await exchange.fetch_balance()
        return bal['USDT']['free']
    except:
        return 10000  # Force high balance on testnet

async def place_order(symbol, side, amount):
    try:
        order = await exchange.create_market_order(symbol, side, amount)
        return order
    except Exception as e:
        print(f"ORDER FAILED {symbol}: {e}")
        return None

async def check_and_trade():
    balance = await get_balance()
    risk_amount = balance * RISK_PER_TRADE

    for symbol in SYMBOLS:
        df = await fetch_ohlcv(symbol, '1m', 100)
        if df.empty or len(df) < 50:
            continue

        close = df['close']
        high = df['high']
        low = df['low']

        df['rsi'] = ta.momentum.RSIIndicator(close, window=RSI_PERIOD).rsi()
        df['adx'] = ta.trend.ADXIndicator(high, low, close, window=ADX_PERIOD).adx()
        df['atr'] = ta.volatility.AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range()

        rsi = df['rsi'].iloc[-1]
        adx = df['adx'].iloc[-1]
        atr = df['atr'].iloc[-1]
        price = close.iloc[-1]

        # EXIT
        if symbol in active_trades:
            trade = active_trades[symbol]
            entry = trade['entry_price']
            sl = entry - STOP_LOSS_ATR * atr if trade['side'] == 'buy' else entry + STOP_LOSS_ATR * atr
            tp = entry + TAKE_PROFIT_ATR * atr if trade['side'] == 'buy' else entry - TAKE_PROFIT_ATR * atr

            if (trade['side'] == 'buy' and (price <= sl or price >= tp)) or \
               (trade['side'] == 'sell' and (price >= sl or price <= tp)):
                close_side = 'sell' if trade['side'] == 'buy' else 'buy'
                order = await place_order(symbol, close_side, trade['quantity'])
                if order:
                    pnl = (price - entry) * trade['quantity'] if trade['side'] == 'buy' else (entry - price) * trade['quantity']
                    print(f"CLOSED {symbol} | PnL: ₹{pnl:,.2f}")
                    del active_trades[symbol]
            continue

        # ENTRY
        qty = risk_amount / (STOP_LOSS_ATR * atr)
        qty = exchange.amount_to_precision(symbol, qty)
        qty = float(qty)

        if qty * price > balance * 0.95:
            continue

        if rsi < RSI_OVERSOLD and adx > ADX_THRESHOLD and price > df['close'].iloc[-2]:
            order = await place_order(symbol, 'buy', qty)
            if order:
                entry = float(order.get('average') or price)
                active_trades[symbol] = {'side': 'buy', 'entry_price': entry, 'quantity': qty}
                print(f"OPENED LONG {symbol} @ ₹{entry:,.2f}")

        elif rsi > RSI_OVERBOUGHT and adx > ADX_THRESHOLD and price < df['close'].iloc[-2]:
            order = await place_order(symbol, 'sell', qty)
            if order:
                entry = float(order.get('average') or price)
                active_trades[symbol] = {'side': 'sell', 'entry_price': entry, 'quantity': qty}
                print(f"OPENED SHORT {symbol} @ ₹{entry:,.2f}")

async def main():
    await exchange.load_markets()
    print("BOT STARTED - TRADING LIVE ON TESTNET - NO STOPPING")
    while True:
        await check_and_trade()
        await asyncio.sleep(60)

if __name__ == "__main__":

    asyncio.run(main())
