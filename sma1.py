import requests
import pandas as pd
import numpy as np
import time
import ta

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

# Penyimpanan status posisi dan sinyal terakhir
positions = {symbol: {'status': None, 'last_signal': None, 'tp': None, 'sl': None} for symbol in symbols}

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
    ema_value = df['EMA200'].iloc[-1]
    if pd.isna(ema_value):
        return 'Indeterminate', 'Tidak Diketahui'
    if df['close'].iloc[-1] > ema_value:
        market_trend = 'Uptrend'
    else:
        market_trend = 'Downtrend'
    if df['SuperTrend'].iloc[-1]:
        signal = 'Beli'
    else:
        signal = 'Jual'
    return signal, market_trend

def cancel_previous_position(symbol):
    prev_pos = positions[symbol]
    if prev_pos['status'] is not None:
        send_telegram_message(f"⚠️ Posisi sebelumnya {prev_pos['status']} pada {symbol} dibatalkan karena sinyal pembalikan.")
        # Reset posisi
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
        for symbol in symbols:
            df = fetch_binance_klines(symbol=symbol)
            df = compute_indicators(df)

            current_price = df['close'].iloc[-1]
            signal, market_trend = determine_signal(df)

            # Ambil posisi sebelumnya
            pos = positions[symbol]
            prev_status = pos['status']
            prev_signal = pos['last_signal']

            # Jika ada sinyal pembalikan, batalkan posisi sebelumnya
            if prev_signal is not None and signal != prev_signal:
                cancel_previous_position(symbol)

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
                    # Jika tidak ada sinyal, lanjut
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

            # Cek TP/SL
            check_tp_sl(symbol, current_price)

        # Delay 5 menit
        time.sleep(300)

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(300)
