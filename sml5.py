import requests
import pandas as pd
import numpy as np
import time
import ta

# Konfigurasi Telegram
TELEGRAM_BOT_TOKEN = '7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48'  # Ganti dengan token bot Telegram Anda
TELEGRAM_CHAT_ID = '6157064978'

# Persentase Take Profit dan Stop Loss
TAKE_PROFIT_PERCENTAGE = 1.5  # 1.5%
STOP_LOSS_PERCENTAGE = 1.0    # 1.0%

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
    df.loc[df['close'] < df['Trailing_Stop'], 'Training_Stop_Signal'] = -1
    df.loc[df['close'] > df['Trailing_Stop'], 'Training_Stop_Signal'] = 1
    return df

def detect_active_signals(df):
    df = compute_supertrend(df)
    df = compute_trailing_stop(df)

    latest_supertrend_signal = df['SuperTrend_signal'].iloc[-1]
    latest_training_stop_signal = df['Training_Stop_Signal'].iloc[-1]
    return latest_supertrend_signal, latest_training_stop_signal

def calculate_levels(entry_price, position_type):
    """
    Menghitung level Take Profit dan Stop Loss berdasarkan posisi dan persentase.
    """
    if position_type == 'Beli':
        tp = entry_price * (1 + TAKE_PROFIT_PERCENTAGE / 100)
        sl = entry_price * (1 - STOP_LOSS_PERCENTAGE / 100)
    else:  # Jual
        tp = entry_price * (1 - TAKE_PROFIT_PERCENTAGE / 100)
        sl = entry_price * (1 + STOP_LOSS_PERCENTAGE / 100)
    return tp, sl

def main():
    df = fetch_binance_klines()

    # Deteksi sinyal aktif
    supertrend_signal, training_stop_signal = detect_active_signals(df)

    # Tentukan posisi berdasarkan sinyal
    if supertrend_signal == 1:
        position = 'Beli'
    else:
        position = 'Jual'

    # Harga entri diambil dari close terakhir
    entry_price = df['close'].iloc[-1]

    # Hitung level TP dan SL
    tp_level, sl_level = calculate_levels(entry_price, position)

    # Kirim pesan ke Telegram tentang sinyal dan level TP/SL
    message = f"🟢 *Sinyal Terbaru:*\n"
    message += f"Posisi: {position}\n"
    message += f"Harga Entri: {entry_price:.2f}\n"
    message += f"Take Profit: {tp_level:.2f}\n"
    message += f"Stop Loss: {sl_level:.2f}\n"
    message += f"Sinyal Training Stop: {'Beli' if training_stop_signal == 1 else 'Jual'}\n"
    send_telegram_message(message)

if __name__ == "__main__":
    main()
