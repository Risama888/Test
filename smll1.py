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
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT']  # Tambahkan sesuai kebutuhan

# Parameter indikator
supertrend_period = 10
supertrend_multiplier = 3

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

def compute_supertrend(df, period=10, multiplier=3):
    atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=period).average_true_range()
    hl2 = (df['high'] + df['low']) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

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
    # Sinyal berdasarkan SuperTrend
    if df['SuperTrend'].iloc[-1]:
        return 'Beli'  # Uptrend
    else:
        return 'Jual'  # Downtrend

# Penyimpanan last signals per coin
last_signals = {symbol: None for symbol in symbols}

while True:
    try:
        tren_turun_coins = []  # Daftar simbol tren turun
        for symbol in symbols:
            # 1. Ambil data terbaru
            df = fetch_binance_klines(symbol=symbol)
            # 2. Hitung indikator SuperTrend
            df = compute_supertrend(df, period=supertrend_period, multiplier=supertrend_multiplier)
            # 3. Tentukan sinyal berdasarkan indikator
            signal = determine_signal(df)
            # 4. Simpan tren turun jika sinyal turun
            if signal == 'Jual':
                tren_turun_coins.append(symbol)
            # 5. Kirim pesan jika sinyal berubah
            if signal != last_signals[symbol]:
                entry_price = df['close'].iloc[-1]
                message = f"📈 *{symbol}*\n"
                message += f"🟢 Sinyal: *{signal}*\n"
                message += f"Harga Saat Ini: {entry_price:.2f}\n"
                message += f"Indikator SuperTrend menunjukkan tren {'Naik' if signal=='Beli' else 'Turun'}.\n"
                send_telegram_message(message)
                last_signals[symbol] = signal

        # 6. Kirim pesan daftar simbol tren turun
        if tren_turun_coins:
            turun_symbols_str = ', '.join(tren_turun_coins)
            message_tren_turun = f"🔻 Tren turun terdeteksi pada: {turun_symbols_str}"
            send_telegram_message(message_tren_turun)

        # Tunggu 5 menit
        time.sleep(30)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(30)
