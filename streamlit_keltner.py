import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="BollM Hisse Tarama", layout="wide")

def calculate_bollinger_bands(df, window=20, std_dev_multiplier=2.0):
    # SMA (Orta Band)
    df['SMA'] = df['Close'].rolling(window=window).mean()
    
    # Standart Sapma
    df['STD'] = df['Close'].rolling(window=window).std()
    
    # Alt ve Üst Bollinger Bandları
    df['Boll_Upper'] = df['SMA'] + (std_dev_multiplier * df['STD'])
    df['Boll_Lower'] = df['SMA'] - (std_dev_multiplier * df['STD'])
    
    return df

def fetch_data(ticker, period='7d', interval='5m'):
    try:
        ticker_symbol = f"{ticker}.IS"
        ticker_obj = yf.Ticker(ticker_symbol)
        
        # Seçilen periyot ve interval (zaman dilimi) ile veri çek
        df = ticker_obj.history(period=period, interval=interval)
        
        # Beklenen en yüksek ve en düşük fiyatlar (Pivot yöntemiyle hesaplamak için 1 günlük veri çekelim)
        df_daily = ticker_obj.history(period='5d', interval='1d')
        
        expected_high, expected_low = None, None
        
        # Eğer dünün verisi tamamsa (Pivot hesaplaması) -> P = (H+L+C)/3, R1 = 2P - L, S1 = 2P - H
        if not df_daily.empty and len(df_daily) >= 2:
            yesterday_data = df_daily.iloc[-2]  # Dünün verisi (son satır bugündür)
            prev_h = yesterday_data['High']
            prev_l = yesterday_data['Low']
            prev_c = yesterday_data['Close']
            
            pivot = (prev_h + prev_l + prev_c) / 3
            expected_high = (2 * pivot) - prev_l
            expected_low = (2 * pivot) - prev_h
            
        if df.empty or len(df) < 30:
            return ticker, None, None, None
            
        df = calculate_bollinger_bands(df)
        return ticker, df, expected_high, expected_low
    except Exception as e:
        return ticker, None, None, None

def plot_stock(ticker, df, tolerance, title_suffix, interval):
    # Eğer "Bugün" seçildiyse grafikte sadece son günün verilerini göster
    if title_suffix == 'Bugün (5 Dakikalık)':
        last_date = df.index[-1].date()
        df_plot = df[df.index.date == last_date]
    else:
        df_plot = df

    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(x=df_plot.index,
                open=df_plot['Open'],
                high=df_plot['High'],
                low=df_plot['Low'],
                close=df_plot['Close'],
                name='Fiyat Mumu'))

    # Bollinger Upper
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Boll_Upper'], 
                             line=dict(color='rgba(255, 0, 0, 0.5)', width=1), 
                             name='Bollinger Üst'))
    
    # SMA
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA'], 
                             line=dict(color='rgba(255, 165, 0, 0.5)', width=1, dash='dash'), 
                             name='SMA (20)'))

    # Bollinger Lower
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Boll_Lower'], 
                             line=dict(color='rgba(0, 128, 0, 0.5)', width=1), 
                             name='Bollinger Alt',
                             fill='tonexty', fillcolor='rgba(128, 128, 128, 0.1)'))
                             
    # GÜÇLÜ AL noktalarını tespit et (fiyat belirlenen toleransa veya daha altına düştüğünde)
    buy_signals = df_plot[((df_plot['Low'] - df_plot['Boll_Lower']) / df_plot['Boll_Lower'] * 100) <= tolerance]
    
    if not buy_signals.empty:
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] - (buy_signals['Low'] * 0.002), # Biraz altına yerleştir
                                 mode='markers+text',
                                 marker=dict(symbol='triangle-up', size=14, color='green'),
                                 text=['GÜÇLÜ AL'] * len(buy_signals),
                                 textposition='bottom center',
                                 textfont=dict(color='green', size=11, family='Arial Black'),
                                 name='Güçlü Al Sinyali'))

    # GÜÇLÜ SAT noktalarını tespit et (fiyat belirlenen toleransa veya daha üstüne çıktığında)
    sell_signals = df_plot[((df_plot['Boll_Upper'] - df_plot['High']) / df_plot['Boll_Upper'] * 100) <= tolerance]
    
    if not sell_signals.empty:
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] + (sell_signals['High'] * 0.002), # Biraz üstüne yerleştir
                                 mode='markers+text',
                                 marker=dict(symbol='triangle-down', size=14, color='red'),
                                 text=['GÜÇLÜ SAT'] * len(sell_signals),
                                 textposition='top center',
                                 textfont=dict(color='red', size=11, family='Arial Black'),
                                 name='Güçlü Sat Sinyali'))

    xaxis_settings = dict(type="date")
    
    rangebreaks = []
    if interval == '5m':
        rangebreaks = [
            dict(bounds=["sat", "mon"]),  # Hafta sonunu gizle
            dict(bounds=[18.2, 9.9], pattern="hour")  # Borsa dışı saatleri gizle
        ]
    elif interval == '1d':
        rangebreaks = [
            dict(bounds=["sat", "mon"])  # Sadece hafta sonunu gizle
        ]
        
    if rangebreaks:
        xaxis_settings['rangebreaks'] = rangebreaks

    fig.update_layout(
        title=f"{ticker} - {title_suffix} Bollinger Bantları",
        yaxis_title="Fiyat (TL)",
        xaxis_title="Zaman",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=0, r=0, t=50, b=0),
        xaxis=xaxis_settings
    )
    
    return fig

def main():
    st.title("📈 Bollinger Bands (BollM) Hisse Tarama & Analiz")
    st.markdown("""
    Bu uygulama, girdiğiniz hisselerin verilerini çeker, 
    Bollinger bantlarını hesaplar ve fiyat Bollinger bantlarında sınır bölgelere belirlenen tolerans mesafesinde yakınsa (veya aştıysa) **Alım/Satım Sinyalleri** tablosunda gösterir.
    """)

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        user_input = st.text_input("Analiz edilecek hisse kodlarını girin:", value="THYAO ASELS GARAN HEDEF ODINE")
    with col2:
        timeframe = st.selectbox("Zaman Dilimi", ["Bugün (5 Dakikalık)", "5 Dakikalık (Son 7 Gün)", "Günlük (Son 6 Ay)", "Haftalık (Son 2 Yıl)"])
    with col3:
        tolerance = st.number_input("Tolerans (%) - Sınır mesafesi", min_value=0.0, max_value=10.0, value=0.5, step=0.1)

    if st.button("Analizi Başlat", type="primary"):
        tickers = [t.strip().upper() for t in re.split(r'[,\s]+', user_input) if t.strip()]

        if not tickers:
            st.warning("Lütfen en az bir hisse kodu girin.")
            return

        # Seçime göre yfinance periyot ve intervallerinin belirlenmesi
        if timeframe == "Bugün (5 Dakikalık)":
            period_val, interval_val, title_suffix = '7d', '5m', 'Bugün (5 Dakikalık)'
        elif timeframe == "5 Dakikalık (Son 7 Gün)":
            period_val, interval_val, title_suffix = '7d', '5m', '5 Dakikalık'
        elif timeframe == "Günlük (Son 6 Ay)":
            period_val, interval_val, title_suffix = '6mo', '1d', 'Günlük'
        else:
            period_val, interval_val, title_suffix = '2y', '1wk', 'Haftalık'

        st.info(f"Toplam {len(tickers)} hisse '{title_suffix}' olarak analiz ediliyor...")
        
        results = []
        graphs = []
        
        progress_bar = st.progress(0)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_data, t, period_val, interval_val) for t in tickers]
            fetched_data = [f.result() for f in futures]
            
        info_data = [] # Tüm analiz edilen hisselerin beklenen seviyeleri tablosu listesi
            
        for i, (ticker, df, expected_high, expected_low) in enumerate(fetched_data):
            progress_bar.progress((i + 1) / len(tickers))
            
            if df is not None:
                # Grafiği hazırla
                graphs.append((ticker, plot_stock(ticker, df, tolerance, title_suffix, interval_val)))
                
                # Sinyal kontrolü
                latest_row = df.iloc[-1]
                current_price = latest_row['Close']
                lower_band = latest_row['Boll_Lower']
                upper_band = latest_row['Boll_Upper']
                
                # Alım (Alt banda yakınlık) ve Satım (Üst banda yakınlık) uzaklıkları
                distance_buy_pct = (current_price - lower_band) / lower_band * 100
                distance_sell_pct = (upper_band - current_price) / upper_band * 100
                
                if distance_buy_pct <= tolerance:
                    results.append({
                        'Hisse': ticker,
                        'Sinyal': '🟢 GÜÇLÜ AL',
                        'Fiyat (TL)': round(current_price, 2),
                        'Hedef Band (TL)': round(lower_band, 2),
                        'Banda Uzaklık (%)': round(distance_buy_pct, 2),
                        'Beklenen Min (Gün)': round(expected_low, 2) if expected_low else '-',
                        'Beklenen Max (Gün)': round(expected_high, 2) if expected_high else '-'
                    })
                elif distance_sell_pct <= tolerance:
                    results.append({
                        'Hisse': ticker,
                        'Sinyal': '🔴 GÜÇLÜ SAT',
                        'Fiyat (TL)': round(current_price, 2),
                        'Hedef Band (TL)': round(upper_band, 2),
                        'Banda Uzaklık (%)': round(distance_sell_pct, 2),
                        'Beklenen Min (Gün)': round(expected_low, 2) if expected_low else '-',
                        'Beklenen Max (Gün)': round(expected_high, 2) if expected_high else '-'
                    })
                    
                info_data.append({
                    'Hisse': ticker,
                    'Güncel Fiyat (TL)': round(current_price, 2),
                    'Öngörülen Min (TL)': round(expected_low, 2) if expected_low else '-',
                    'Öngörülen Max (TL)': round(expected_high, 2) if expected_high else '-'
                })
            else:
                st.error(f"{ticker} verisi çekilemedi veya yetersiz (7 günlük 5D).")

        st.success("Analiz tamamlandı!")
        
        st.subheader("📊 Günlük Beklenen Min-Max Fiyatlar")
        if info_data:
            st.dataframe(pd.DataFrame(info_data), use_container_width=True)

        st.subheader("🎯 Mevcut Alım / Satım Sinyali Veren Hisseler")
        if results:
            results_df = pd.DataFrame(results)
            # Farka göre sırala (En az farka sahip olan -en sınırda olan- en üstte)
            results_df = results_df.sort_values(by='Banda Uzaklık (%)').reset_index(drop=True)
            st.dataframe(results_df, use_container_width=True)
        else:
            st.warning(f"Şu anki güncel fiyatlarda, Bollinger bantlarına %{tolerance} yakınlığında bir hisse bulunamadı.")

        st.subheader("📊 Hisse Grafikleri")
        for ticker, fig in graphs:
            st.plotly_chart(fig, use_container_width=True)

if __name__ == '__main__':
    main()
