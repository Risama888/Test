import requests
import pandas as pd
import numpy as np
import time
import ta
from datetime import datetime, timedelta
import os

# Konfigurasi Telegram
TELEGRAM_BOT_TOKEN = '7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48'  # Ganti dengan token bot Telegram Anda
TELEGRAM_CHAT_ID = '6157064978'      # Ganti dengan chat ID Anda

# Daftar pasangan mata uang
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

# Parameter indikator
supertrend_period = 10
supertrend_multiplier = 3
ema_period = 200
tp_percentage = 0.02  # 2%
sl_percentage = 0.01  # 1%

# File untuk menyimpan sinyal yang sudah dikirim
signal_log_file = 'signal_log.txt'

# Penyimpanan status posisi dan sinyal terakhir
positions = {symbol: {'status': None, 'last_signal': None, 'tp': None, 'sl': None} for symbol in symbols}

# Variabel untuk mengontrol pengiriman market trend setiap 30 menit
last_market_update = datetime.min

# Fungsi membaca sinyal dari file
def read_sent_signals():
    sent_signals = set()
    if os.path.exists(signal_log_file):
        try:
            with open(signal_log_file, 'r') as f:
                for line in f:
                    sent_signals.add(line.strip())
        except Exception as e:
            print(f"Error membaca file log: {e}")
    return sent_signals

# Fungsi menambahkan sinyal ke file
def log_signal(signal_message):
    try:
        with open(signal_log_file, 'a') as f:
            f.write(signal_message + '\n')
    except Exception as e:
        print(f"Error menulis ke file log: {e}")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"Gagal kirim pesan Telegram: {response.text}")
    except Exception as e:
        print(f"Gagal mengirim pesan: {e}")

def fetch_binance_klines(symbol='BTCUSDT', interval='30m', limit=500):
    url = 'https://api.binance.com/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            print(f"Tidak ada data dari Binance untuk {symbol}")
            return pd.DataFrame()
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
    except Exception as e:
        print(f"Error fetching data {symbol}: {e}")
        return pd.DataFrame()

def compute_indicators(df):
    if df.empty:
        return df
    try:
        df['EMA200'] = ta.trend.ema_indicator(df['close'], window=200)
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

            if supertrend[-1]:
                lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
            else:
                upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])

        df['SuperTrend'] = supertrend
        return df
    except Exception as e:
        print(f"Error computing indicators: {e}")
        return df

def determine_signal(df):
    if df.empty:
        return 'Indeterminate', 'Tidak Diketahui', 'Tidak Diketahui'
    try:
        ema_value = df['EMA200'].iloc[-1]
        current_close = df['close'].iloc[-1]
        if pd.isna(ema_value):
            market_trend = 'Tidak Diketahui'
        else:
            market_trend = 'Uptrend' if current_close > ema_value else 'Downtrend'
        supertrend_value = df['SuperTrend'].iloc[-1]
        signal = 'Beli' if supertrend_value else 'Jual'
        return signal, market_trend, ema_value
    except Exception as e:
        print(f"Error determining signal: {e}")
        return 'Indeterminate', 'Tidak Diketahui', 'Tidak Diketahui'

def cancel_previous_position(symbol):
    prev_pos = positions[symbol]
    if prev_pos['status'] is not None:
        send_telegram_message(f"⚠️ Posisi sebelumnya {prev_pos['status']} pada {symbol} dibatalkan karena sinyal pembalikan.")
        positions[symbol] = {'status': None, 'last_signal': None, 'tp': None, 'sl': None}

def check_tp_sl(symbol, current_price):
    pos = positions[symbol]
    if pos['status'] == 'Long':
        if current_price >= pos['tp']:
            send_telegram_message(f"✅ {symbol} mencapai Take Profit (Long) di {current_price:.2f}")
            pos['status'] = None
        elif current_price <= pos['sl']:
            send_telegram_message(f"❌ {symbol} terkena Stop Loss (Long) di {current_price:.2f}")
            pos['status'] = None
    elif pos['status'] == 'Short':
        if current_price <= pos['tp']:
            send_telegram_message(f"✅ {symbol} mencapai Take Profit (Short) di {current_price:.2f}")
            pos['status'] = None
        elif current_price >= pos['sl']:
            send_telegram_message(f"❌ {symbol} terkena Stop Loss (Short) di {current_price:.2f}")
            pos['status'] = None

while True:
    try:
        now = datetime.now()
        # Cek apakah sudah 30 menit dari pengiriman terakhir
        if now - last_market_update >= timedelta(minutes=30):
            sent_signals = read_sent_signals()
            for symbol in symbols:
                df = fetch_binance_klines(symbol=symbol)
                if df.empty:
                    print(f"Tidak ada data untuk {symbol}, skip.")
                    continue
                df = compute_indicators(df)
                current_price = df['close'].iloc[-1]
                _, market_trend, ema_value = determine_signal(df)

                # Kirim info market trend setiap 30 menit jika belum pernah dikirim
                message_trend = f"*{symbol}*\nMarket saat ini: *{market_trend}*\n"
                if not pd.isna(ema_value):
                    message_trend += f"EMA 200: {ema_value:.2f}\n"

                # Cek apakah sudah pernah dikirim
                if message_trend not in sent_signals:
                    send_telegram_message(message_trend)
                    log_signal(message_trend)

            last_market_update = now

        # Proses pengelolaan posisi untuk setiap simbol
        for symbol in symbols:
            df = fetch_binance_klines(symbol=symbol)
            if df.empty:
                print(f"Tidak ada data untuk {symbol}, skip.")
                continue
            df = compute_indicators(df)
            current_price = df['close'].iloc[-1]
            signal, market_trend, ema_value = determine_signal(df)

            # Ambil posisi sebelumnya
            pos = positions[symbol]
            prev_status = pos['status']
            prev_signal = pos['last_signal']

            # Jika ada sinyal pembalikan, batalkan posisi sebelumnya
            if prev_signal is not None and signal != prev_signal:
                cancel_previous_position(symbol)

            # Buat pesan sinyal
            message_signal = f"{symbol} - Sinyal: {signal}"

            # Cek apakah sinyal sudah pernah dikirim
            sent_signals = read_sent_signals()  # baca lagi agar update terbaru
            if message_signal in sent_signals:
                # Sinyal sudah pernah dikirim, skip
                continue

            # Jika sinyal berbeda dari terakhir, buat posisi baru
            if signal != prev_signal:
                if signal == 'Beli':
                    pos['status'] = 'Long'
                    pos['last_signal'] = 'Beli'
                    tp_price = current_price * (1 + tp_percentage)
                    sl_price = current_price * (1 - sl_percentage)
                elif signal == 'Jual':
                    pos['status'] = 'Short'
                    pos['last_signal'] = 'Jual'
                    tp_price = current_price * (1 - tp_percentage)
                    sl_price = current_price * (1 + sl_percentage)
                else:
                    continue

                # Simpan TP dan SL
                pos['tp'] = tp_price
                pos['sl'] = sl_price

                # Kirim notifikasi posisi terbuka
                message = f"🚀 {symbol} membuka posisi {pos['status']}\n"
                message += f"Harga Entry: {current_price:.2f}\n"
                message += f"TP: {tp_price:.2f}\n"
                message += f"SL: {sl_price:.2f}"
                send_telegram_message(message)
                # Log sinyal ini
                log_signal(message)

            # Cek TP/SL
            check_tp_sl(symbol, current_price)

        # Delay 5 menit
        time.sleep(30)

    except Exception as e:
        print(f"Error utama: {e}")
        time.sleep(30)
