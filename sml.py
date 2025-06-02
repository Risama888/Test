import requests
import pandas as pd
import numpy as np
import time
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

# Fungsi utama untuk menjalankan trading simulasi
def trading_simulation(df, initial_balance=1000, take_profit_pct=0.02, stop_loss_pct=0.01):
    balance = initial_balance
    position = None  # 'long' atau 'short' atau None
    entry_price = 0
    trade_log = []

    for i in range(1, len(df)):
        price = df['close'].iloc[i]
        prev_row = df.iloc[i-1]
        signal = None

        # Tentukan sinyal dari indikator
        if df['SuperTrend'].iloc[i] and df['Training_Stop_Signal'].iloc[i] == 1:
            signal = 'buy'
        elif not df['SuperTrend'].iloc[i] and df['Training_Stop_Signal'].iloc[i] == -1:
            signal = 'sell'

        # Jika sinyal buy dan tidak posisi terbuka
        if signal == 'buy' and position != 'long':
            entry_price = price
            take_profit = entry_price * (1 + take_profit_pct)
            stop_loss = entry_price * (1 - stop_loss_pct)
            position = 'long'
            trade_log.append({
                'type': 'buy',
                'price': entry_price,
                'tp': take_profit,
                'sl': stop_loss,
                'timestamp': df.index[i]
            })
            print(f"Buy at {entry_price:.2f} on {df.index[i]}")

        # Jika posisi long dan harga mencapai TP atau SL
        if position == 'long':
            if price >= trade_log[-1]['tp']:
                profit = price - trade_log[-1]['price']
                balance += profit
                print(f"Take Profit at {price:.2f} on {df.index[i]}, Profit: {profit:.2f}")
                position = None
            elif price <= trade_log[-1]['sl']:
                loss = trade_log[-1]['price'] - price
                balance -= loss
                print(f"Stop Loss at {price:.2f} on {df.index[i]}, Loss: {loss:.2f}")
                position = None

        # Jika sinyal jual dan posisi tidak long
        if signal == 'sell' and position != 'short':
            entry_price = price
            take_profit = entry_price * (1 - take_profit_pct)
            stop_loss = entry_price * (1 + stop_loss_pct)
            position = 'short'
            trade_log.append({
                'type': 'sell',
                'price': entry_price,
                'tp': take_profit,
                'sl': stop_loss,
                'timestamp': df.index[i]
            })
            print(f"Sell at {entry_price:.2f} on {df.index[i]}")

        # Jika posisi short dan harga mencapai TP atau SL
        if position == 'short':
            if price <= trade_log[-1]['tp']:
                profit = trade_log[-1]['price'] - price
                balance += profit
                print(f"Take Profit at {price:.2f} on {df.index[i]}, Profit: {profit:.2f}")
                position = None
            elif price >= trade_log[-1]['sl']:
                loss = price - trade_log[-1]['price']
                balance -= loss
                print(f"Stop Loss at {price:.2f} on {df.index[i]}, Loss: {loss:.2f}")
                position = None

        # Optional: Bisa tambahkan log posisi saat ini

    print(f"Ending Balance: {balance:.2f}")
    return trade_log, balance

# Main proses
def main():
    df = fetch_binance_klines()
    df = compute_supertrend(df)
    df = compute_trailing_stop(df)

    # Melatih model ML
    df['return'] = df['close'].pct_change()
    df['supertrend'] = df['SuperTrend'].astype(int)
    df['training_stop'] = df['Training_Stop_Signal']
    df.dropna(inplace=True)

    X = df[['return', 'supertrend', 'training_stop']]
    y = df['SuperTrend_signal']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    # Loop untuk simulasi trading
    for _ in range(3):  # Ulang 3 kali, bisa diatur sesuai kebutuhan
        y_pred = clf.predict(X)
        df['Predicted_Signal'] = y_pred

        # Jalankan simulasi trading berdasarkan sinyal
        trade_log, final_balance = trading_simulation(df, initial_balance=1000)
        print(f"Final Balance: {final_balance:.2f}")
        time.sleep(10)  # Tunggu 10 detik sebelum ulang (bisa disesuaikan)

if __name__ == "__main__":
    main()
