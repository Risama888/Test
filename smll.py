import requests
import pandas as pd
import numpy as np
import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import ta

# Konfigurasi Telegram
TELEGRAM_BOT_TOKEN = '7795073622:AAFEHjnKKNAUv2SEwkhLpvblMqolLNjSP48'  # Ganti dengan token bot Telegram Anda
TELEGRAM_CHAT_ID = '6157064978'      # Ganti dengan chat ID Anda

# Persentase TP dan SL
TAKE_PROFIT_PERCENTAGE = 1.5
STOP_LOSS_PERCENTAGE = 1.0

# Daftar pasangan mata uang yang ingin diprediksi
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT']  # Tambahkan sesuai kebutuhan

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
    df['SuperTrend_signal'] = df['SuperTrend'].astype(int)
    return df

def compute_trailing_stop(df, window=5):
    df['Trailing_Stop'] = df['close'].rolling(window=window).min()
    df['Trailing_Stop_Signal'] = 0
    df.loc[df['close'] < df['Trailing_Stop'], 'Trailing_Stop_Signal'] = -1
    df.loc[df['close'] > df['Trailing_Stop'], 'Trailing_Stop_Signal'] = 1
    return df

def prepare_training_data(df):
    df = df.copy()
    df['future_close'] = df['close'].shift(-1)
    df.dropna(inplace=True)
    df['signal'] = np.where(df['future_close'] > df['close'], 1, 0)  # 1=Beli, 0=Jual

    features = {
        'close': df['close'],
        'high': df['high'],
        'low': df['low'],
        'volume': df['volume'],
        'supertrend': df['SuperTrend'].astype(int),
        'trailing_stop': np.where(df['close'] > df['Trailing_Stop'], 1, 0)
    }
    X = pd.DataFrame(features)
    y = df['signal']
    return X, y

def train_model(X, y):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    print("Model dilatih dari data terbaru.")
    return model

def calculate_levels(entry_price, position):
    if position == 'Beli':
        tp = entry_price * (1 + TAKE_PROFIT_PERCENTAGE / 100)
        sl = entry_price * (1 - STOP_LOSS_PERCENTAGE / 100)
    else:
        tp = entry_price * (1 - TAKE_PROFIT_PERCENTAGE / 100)
        sl = entry_price * (1 + STOP_LOSS_PERCENTAGE / 100)
    return tp, sl

# Penyimpanan last signals per coin
last_signals = {symbol: None for symbol in symbols}
models = {symbol: None for symbol in symbols}

while True:
    try:
        for symbol in symbols:
            # 1. Ambil data terbaru
            df = fetch_binance_klines(symbol=symbol)
            # 2. Hitung indikator
            df = compute_supertrend(df)
            df = compute_trailing_stop(df)
            # 3. Siapkan data training dari data terbaru
            X, y = prepare_training_data(df)
            # 4. Latih model dari data terbaru
            model = train_model(X, y)
            models[symbol] = model

            # 5. Siapkan fitur prediksi dari data terbaru
            feature_df = pd.DataFrame({
                'close': [df['close'].iloc[-1]],
                'high': [df['high'].iloc[-1]],
                'low': [df['low'].iloc[-1]],
                'volume': [df['volume'].iloc[-1]],
                'supertrend': [1 if df['SuperTrend'].iloc[-1] else 0],
                'trailing_stop': [1 if df['close'].iloc[-1] > df['Trailing_Stop'].iloc[-1] else 0]
            })

            # 6. Prediksi sinyal
            predicted_signal = model.predict(feature_df)[0]

            # 7. Kirim notifikasi jika sinyal berbeda
            if predicted_signal != last_signals[symbol]:
                position = 'Beli' if predicted_signal == 1 else 'Jual'
                entry_price = df['close'].iloc[-1]
                tp, sl = calculate_levels(entry_price, position)

                message = f"📈 *{symbol}*\n"
                message += f"🟢 Sinyal: {position}\n"
                message += f"Harga Entri: {entry_price:.2f}\n"
                message += f"Take Profit: {tp:.2f}\n"
                message += f"Stop Loss: {sl:.2f}\n"

                send_telegram_message(message)
                last_signals[symbol] = predicted_signal

        # Tunggu 5 menit sebelum update lagi
        time.sleep(30)

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(30)
