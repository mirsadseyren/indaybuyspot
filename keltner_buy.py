import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import os
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

def calculate_bollinger_bands(df, window=20, std_dev_multiplier=2.0):
    """
    Bollinger Bands (BollM) hesaplayan fonksiyon.
    Orta Band: 20 periyotluk SMA
    Üst Band: SMA + (Multiplier * STD)
    Alt Band: SMA - (Multiplier * STD)
    """
    # SMA (Orta Band)
    df['SMA'] = df['Close'].rolling(window=window).mean()
    
    # Standart Sapma
    df['STD'] = df['Close'].rolling(window=window).std()
    
    # Alt ve Üst Bollinger Bandları
    df['Boll_Upper'] = df['SMA'] + (std_dev_multiplier * df['STD'])
    df['Boll_Lower'] = df['SMA'] - (std_dev_multiplier * df['STD'])
    
    return df

def analyze_stock(ticker):
    try:
        # BIST için sonuna .IS ekliyoruz ve 5 dakikalık 7 günlük veri çekiyoruz
        ticker_symbol = f"{ticker}.IS"
        ticker_obj = yf.Ticker(ticker_symbol)
        df = ticker_obj.history(period='7d', interval='5m')
        
        if df.empty or len(df) < 30:
            print(f"[DEBUG] {ticker}: Veri bulunamadı veya yetersiz satır ({len(df)} satır).")
            return None
            
        df = calculate_bollinger_bands(df)
        
        # Son güncel mumdaki veriler
        latest_row = df.iloc[-1]
        current_price = latest_row['Close']
        lower_band = latest_row['Boll_Lower']
        
        # Mükemmel alım pozisyonunu tespit etmek:
        # Fiyatın alt bandın %0.5 kadar yakınında veya altında olması şartı
        distance_pct = (current_price - lower_band) / lower_band * 100
        
        print(f"[DEBUG] {ticker}: Son Fiyat: {current_price:.2f}, Alt Band: {lower_band:.2f}, Uzaklık: %{distance_pct:.2f}")

        # %0.5 tolerans verdik, dilerseniz bu sayıyı değiştirebilirsiniz
        if distance_pct <= 0.5:
            return {
                'Hisse': ticker,
                'Fiyat': float(current_price),
                'Alım Limiti': float(lower_band),
                'Fark (%)': float(distance_pct)
            }
            
    except Exception as e:
        print(f"[DEBUG] {ticker}: Hata oluştu -> {e}")
        
    return None

import re

def main():
    user_input = input("Lütfen analiz edilecek hisse kodlarını aralarında virgül veya boşluk bırakarak girin (Örn: THYAO ASELS GARAN): ")
    tickers = [t.strip().upper() for t in re.split(r'[,\s]+', user_input) if t.strip()]

    if not tickers:
        print("Hisse kodu girmediniz. Program sonlandırılıyor.")
        return

    print(f"Toplam {len(tickers)} hisse analiz ediliyor (5 dakikalık periyot, 7 günlük lookback).")
    print("Mükemmel alım noktasını (Bollinger alt bandı) bulan tarama başlatıldı. Lütfen bekleyin...\n")
    
    results = []
    # Çoklu iş parçacığıyla (multithreading) indirmeyi hızlandırıyoruz
    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(analyze_stock, tickers):
            if res:
                results.append(res)
                
    # Farka göre sıralama (en negatif olanın fiyatı alt bandın en altındadır, daha oversold demektir)
    results.sort(key=lambda x: x['Fark (%)'])
    
    if not results:
        print("Şu anda Bollinger alt bandına yeterince yakın veya altında olan hisse bulunamadı.")
    else:
        print(f"{'Hisse':<10} | {'Fiyat':<10} | {'Alım Limit Fiyatı':<20} | {'Banda Uzaklık (%)':<15}")
        print("-" * 65)
        for r in results:
            print(f"{r['Hisse']:<10} | {r['Fiyat']:<10.2f} | {r['Alım Limiti']:<20.2f} | {r['Fark (%)']:<15.2f}")

if __name__ == '__main__':
    main()
