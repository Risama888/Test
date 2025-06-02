import requests
import pandas as pd
import numpy as np
import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import ta
import os

# Konfigurasi Telegram
TELEGRAM_BOT_TOKEN = '7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48'  # Ganti dengan token bot Telegram Anda
TELEGRAM_CHAT_ID = '6157064978'      # Ganti dengan chat ID Anda

LOG_FILE = 'trade_log.csv'

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Gagal mengirim pesan: {response.text}")

def fetch_binance_klines(symbol='BTCUSDT', interval='30m', limit=500):
    url = 'https://api.binance.com/api/v3/klines'
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
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
    # Hitung ATR
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

        # Adjust bands
        if supertrend[-1]:
            lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
        else:
            upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])

    df['SuperTrend'] = supertrend
    df['SuperTrend_signal'] = df['SuperTrend'].astype(int).replace({1:1, 0:0})
    return df

def compute_trailing_stop(df, window=5):
    df['Trailing_Stop'] = df['close'].rolling(window=window).min()
    df['Training_Stop_Signal'] = 0
    df.loc[df['close'] < df['Trailing_Stop'], 'Training_Stop_Signal'] = -1  # Jual
    df.loc[df['close'] > df['Trailing_Stop'], 'Training_Stop_Signal'] = 1   # Beli
    return df

def detect_active_signals(df):
    df = compute_supertrend(df)
    df = compute_trailing_stop(df)

    supertrend_signals = df['SuperTrend_signal']
    training_stop_signals = df['Training_Stop_Signal']

    latest_supertrend_signal = supertrend_signals.iloc[-1]
    latest_training_stop_signal = training_stop_signals.iloc[-1]

    # Cari indeks mulai sinyal aktif terakhir
    last_supertrend_idx = 0
    for i in range(len(supertrend_signals)-1, -1, -1):
        if supertrend_signals.iloc[i] != latest_supertrend_signal:
            last_supertrend_idx = i + 1
            break

    last_training_stop_idx = 0
    for i in range(len(training_stop_signals)-1, -1, -1):
        if training_stop_signals.iloc[i] != latest_training_stop_signal:
            last_training_stop_idx = i + 1
            break

    return {
        'latest_supertrend_signal': latest_supertrend_signal,
        'active_supertrend_index': last_supertrend_idx,
        'latest_training_stop_signal': latest_training_stop_signal,
        'active_training_stop_index': last_training_stop_idx
    }

def load_trade_log():
    if os.path.exists(LOG_FILE):
        return pd.read_csv(LOG_FILE)
    else:
        # Jika file tidak ada, buat DataFrame baru
        return pd.DataFrame(columns=['timestamp', 'supertrend_signal', 'training_stop_signal', 'trade_type'])

def save_trade_log(df_log):
    df_log.to_csv(LOG_FILE, index=False)

def add_trade_log(entry):
    df_log = load_trade_log()
    # Cek entri terakhir untuk menghindari duplikasi
    if not df_log.empty:
        last_entry = df_log.iloc[-1]
        if (last_entry['supertrend_signal'] == entry['supertrend_signal'] and
            last_entry['training_stop_signal'] == entry['training_stop_signal']):
            # Entri sama, tidak perlu menambah
            return
    # Tambahkan entri baru
    df_new = pd.DataFrame([entry])
    df_log = pd.concat([df_log, df_new], ignore_index=True)
    save_trade_log(df_log)

def main():
    # Ambil data
    df = fetch_binance_klines()

    # Deteksi sinyal aktif dan terbaru
    signals = detect_active_signals(df)

    # Tentukan tipe trade berdasarkan sinyal terbaru
    trade_type = 'Beli' if signals['latest_supertrend_signal'] == 1 else 'Jual'

    # Tambahkan entri ke trade log jika berbeda dengan terakhir
    log_entry = {
        'timestamp': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        'supertrend_signal': signals['latest_supertrend_signal'],
        'training_stop_signal': signals['latest_training_stop_signal'],
        'trade_type': trade_type
    }
    add_trade_log(log_entry)

    # Kirim pesan ke Telegram
    message = f"🟢 *Sinyal Terbaru:*\n"
    message += f"SuperTrend: {'Beli' if signals['latest_supertrend_signal'] == 1 else 'Jual'}\n"
    message += f"Training Stop: {'Beli' if signals['latest_training_stop_signal'] == 1 else 'Jual'}\n"
    message += f"Log Entry Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_telegram_message(message)

    print("Pesan dan trade log telah diperbarui dan dikirim.")

if __name__ == "__main__":
    main()
