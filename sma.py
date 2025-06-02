import requests
import pandas as pd
import numpy as np
import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import ta

# Konfigurasi Telegram
TELEGRAM_BOT_TOKEN = '7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48'  # Ganti dengan token bot Telegram Anda
TELEGRAM_CHAT_ID = '6157064978'      # Ganti dengan chat ID Anda

# Daftar pasangan mata uang
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRP']  # Tambahkan sesuai kebutuhan

# Parameter indikator
supertrend_period = 10
supertrend_multiplier = 3
ema_period = 200
tp_percentage = 0.02  # 2%
sl_percentage = 0.01  # 1%

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Gagal mengirim pesan: {e}")

def fetch_binance_klines(symbol='BTCUSDT', interval='30m', limit=500):
    url = 'https://api.binance.com/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df.set_index('open_time', inplace=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])
    return df

def compute_indicators(df):
    # EMA 200
    df['EMA200'] = ta.trend.ema_indicator(df['close'], window=200)
    # SuperTrend
    atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=supertrend_period).average_true_range()
    hl2 = (df['high'] + df['low']) / 2
    upperband = hl2 + (supertrend_multiplier * atr)
    lowerband = hl2 - (supertrend_multiplier * atr)

    supertrend = [True]
    for i in range(1, len(df)):
        curr_close = df['close'].iloc[i]
        prev_supertrend = supertrend[-1]
        prev_upperband = upperband.iloc[i-1]
        prev_lowerband = lowerband.iloc[i-1]

        if curr_close > prev_upperband:
            supertrend.append(True)
        elif curr_close < prev_lowerband:
            supertrend.append(False)
        else:
            supertrend.append(prev_supertrend)

        # Penyesuaian band
        if supertrend[-1]:
            lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
        else:
            upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])

    df['SuperTrend'] = supertrend
    return df

def determine_signal(df):
    # Jika EMA200 menunjukkan downtrend, prioritas turun
    ema_value = df['EMA200'].iloc[-1]
    if pd.isna(ema_value):
        return 'Indeterminate', 'Tidak Diketahui'
    if df['close'].iloc[-1] > ema_value:
        market_trend = 'Uptrend'
    else:
        market_trend = 'Downtrend'
    # Sinyal berdasarkan SuperTrend
    if df['SuperTrend'].iloc[-1]:
        signal = 'Beli'
    else:
        signal = 'Jual'
    return signal, market_trend

# Penyimpanan last signals per coin
last_signals = {symbol: None for symbol in symbols}

while True:
    try:
        tren_turun_coins = []  # Daftar simbol tren turun
        for symbol in symbols:
            df = fetch_binance_klines(symbol=symbol)
            df = compute_indicators(df)
            signal, market_trend = determine_signal(df)
            entry_price = df['close'].iloc[-1]
            ema_value = df['EMA200'].iloc[-1]
            # Tentukan arah pasar utama
            if pd.isna(ema_value):
                market_direction = 'Tidak Diketahui'
            elif entry_price > ema_value:
                market_direction = 'Uptrend'
            else:
                market_direction = 'Downtrend'

            # Cek tren turun
            if signal == 'Jual':
                tren_turun_coins.append(symbol)

            # Kirim pesan hanya jika sinyal berbeda dari terakhir
            if signal != last_signals[symbol]:
                # Hitung TP dan SL
                tp_price = entry_price * (1 + tp_percentage) if signal == 'Beli' else entry_price * (1 - tp_percentage)
                sl_price = entry_price * (1 - sl_percentage) if signal == 'Beli' else entry_price * (1 + sl_percentage)
                message = f"📈 *{symbol}*\n"
                message += f"🟢 Sinyal: *{signal}*\n"
                message += f"Harga Saat Ini: {entry_price:.2f}\n"
                message += f"Market Trend Utama: {market_direction}\n"
                message += f"Indikator SuperTrend menunjukkan tren: {'Naik' if signal=='Beli' else 'Turun'}.\n"
                message += f"TP: {tp_price:.2f}\n"
                message += f"SL: {sl_price:.2f}\n"
                send_telegram_message(message)
                # Update last signal
                last_signals[symbol] = signal

        # Kirim info tren turun
        if tren_turun_coins:
            turun_symbols_str = ', '.join(tren_turun_coins)
            message_tren_turun = f"🔻 Tren turun terdeteksi pada: {turun_symbols_str}"
            send_telegram_message(message_tren_turun)

        # Tunggu 5 menit
        time.sleep(30)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(30)
