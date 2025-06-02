import requests
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import ta

# Fungsi untuk mengambil data 30 menit dari Binance
def fetch_binance_klines(symbol='BTCUSDT', interval='30m', limit=500):
    url = f'https://api.binance.com/api/v3/klines'
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

    # Ubah kolom ke tipe numerik
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    return df

# Hitung SuperTrend
def compute_supertrend(df, period=10, multiplier=3):
    atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=period).average_true_range()
    hl2 = (df['high'] + df['low']) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    supertrend = [True] * len(df)
    for i in range(1, len(df)):
        curr_close = df['close'].iloc[i]
        prev_supertrend = supertrend[i-1]
        prev_upperband = upperband.iloc[i-1]
        prev_lowerband = lowerband.iloc[i-1]
        if curr_close > prev_upperband:
            supertrend[i] = True
        elif curr_close < prev_lowerband:
            supertrend[i] = False
        else:
            supertrend[i] = prev_supertrend

        # Adjust bands
        if supertrend[i]:
            lowerband.iloc[i] = max(lowerband.iloc[i], lowerband.iloc[i-1])
        else:
            upperband.iloc[i] = min(upperband.iloc[i], upperband.iloc[i-1])

    df['SuperTrend'] = supertrend
    df['SuperTrend_signal'] = 1
    df.loc[df['SuperTrend'] == False, 'SuperTrend_signal'] = 0
    return df

# Hitung Training Stop (Trailing Stop)
def compute_trailing_stop(df, window=5):
    df['Trailing_Stop'] = df['close'].rolling(window=window).min()
    df['Training_Stop_Signal'] = 0
    df.loc[df['close'] < df['Trailing_Stop'], 'Training_Stop_Signal'] = -1  # Jual
    df.loc[df['close'] > df['Trailing_Stop'], 'Training_Stop_Signal'] = 1   # Beli
    return df

# Main
df = fetch_binance_klines()

# Hitung indikator
df = compute_supertrend(df)
df = compute_trailing_stop(df)

# Buat fitur dan target
df['return'] = df['close'].pct_change()
df['supertrend'] = df['SuperTrend'].astype(int)
df['training_stop'] = df['Training_Stop_Signal']

# Drop missing values
df.dropna(inplace=True)

# Fitur dan target
X = df[['return', 'supertrend', 'training_stop']]
y = df['SuperTrend_signal']

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

# Latih model
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

# Prediksi
y_pred = clf.predict(X_test)

# Evaluasi
print(classification_report(y_test, y_pred))

# Prediksi sinyal terbaru
latest_features = X.iloc[-1].values.reshape(1, -1)
predicted_signal = clf.predict(latest_features)

if predicted_signal == 1:
    print("Sinyal Beli (Buy)")
else:
    print("Sinyal Jual (Sell)")
