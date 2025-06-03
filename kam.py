import sqlite3
import requests
import pandas as pd
import ta
import time
from datetime import datetime, timedelta

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

# Database setup
conn = sqlite3.connect('signals.db')
c = conn.cursor()

# Buat tabel jika belum ada
c.execute('''
CREATE TABLE IF NOT EXISTS sent_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_text TEXT UNIQUE,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.commit()

def is_signal_sent(signal_text):
    c.execute("SELECT 1 FROM sent_signals WHERE signal_text = ?", (signal_text,))
    return c.fetchone() is not None

def log_signal(signal_text):
    try:
        c.execute("INSERT INTO sent_signals (signal_text) VALUES (?)", (signal_text,))
        conn.commit()
    except sqlite3.IntegrityError:
        # Sinyal sudah ada
        pass

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
    # Logika untuk membatalkan posisi sebelumnya, bisa disesuaikan
    send_telegram_message(f"⚠️ Posisi sebelumnya pada {symbol} dibatalkan karena sinyal berbalik.")

def check_tp_sl(symbol, current_price):
    # Implementasi cek TP/SL, tergantung posisi yang dibuka
    pass  # bisa disesuaikan sesuai kebutuhan

# Variabel kontrol waktu
last_market_update = datetime.min

while True:
    try:
        now = datetime.now()
        # Kirim info market setiap 30 menit
        if now - last_market_update >= timedelta(minutes=30):
            for symbol in symbols:
                df = fetch_binance_klines(symbol=symbol)
                if df.empty:
                    continue
                df = compute_indicators(df)
                _, market_trend, ema_value = determine_signal(df)
                message_trend = f"*{symbol}*\nMarket saat ini: *{market_trend}*\n"
                if not pd.isna(ema_value):
                    message_trend += f"EMA 200: {ema_value:.2f}\n"

                # Cek dan kirim jika belum pernah
                if not is_signal_sent(message_trend):
                    send_telegram_message(message_trend)
                    log_signal(message_trend)

            last_market_update = now

        # Proses pengelolaan posisi dan sinyal
        for symbol in symbols:
            df = fetch_binance_klines(symbol=symbol)
            if df.empty:
                continue
            df = compute_indicators(df)
            current_price = df['close'].iloc[-1]
            signal, market_trend, ema_value = determine_signal(df)

            # Cek posisi sebelumnya
            prev_signal = None
            # Jika Anda ingin menyimpan posisi di database, bisa tambahkan di sini

            # Buat pesan sinyal
            message_signal = f"{symbol} - Sinyal: {signal}"

            # Cek apakah sinyal ini sudah pernah dikirim
            if is_signal_sent(message_signal):
                continue  # sudah pernah, skip

            # Jika berbeda dari sinyal sebelumnya
            # Implementasi logika posisi dan TP/SL bisa ditambahkan di sini
            # Untuk contoh, kita kirim dan catat sinyal baru
            send_telegram_message(message_signal)
            log_signal(message_signal)

            # Implementasi pengaturan TP/SL dan posisi bisa ditambahkan di sini

        # Delay 5 menit
        time.sleep(30)

    except Exception as e:
        print(f"Error utama: {e}")
        time.sleep(30)
