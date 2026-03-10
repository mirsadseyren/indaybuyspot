import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="Keltner Channel Hisse Tarama", layout="wide")

def calculate_keltner_channels(df, ema_period=20, atr_period=14, multiplier=2.0):
    # EMA (Orta Band)
    df['EMA'] = df['Close'].ewm(span=ema_period, adjust=False).mean()
    
    # True Range (TR)
    df['Previous_Close'] = df['Close'].shift(1)
    df['High-Low'] = df['High'] - df['Low']
    df['High-PrevClose'] = abs(df['High'] - df['Previous_Close'])
    df['Low-PrevClose'] = abs(df['Low'] - df['Previous_Close'])
    df['TR'] = df[['High-Low', 'High-PrevClose', 'Low-PrevClose']].max(axis=1)
    
    # ATR Hesaplaması (TR'nin basit hareketli ortalaması)
    df['ATR'] = df['TR'].rolling(window=atr_period).mean()
    
    # Alt ve Üst Keltner Bandları
    df['Keltner_Upper'] = df['EMA'] + (multiplier * df['ATR'])
    df['Keltner_Lower'] = df['EMA'] - (multiplier * df['ATR'])
    
    return df

def fetch_data(ticker):
    try:
        ticker_symbol = f"{ticker}.IS"
        ticker_obj = yf.Ticker(ticker_symbol)
        df = ticker_obj.history(period='7d', interval='5m')
        
        if df.empty or len(df) < 30:
            return ticker, None
            
        df = calculate_keltner_channels(df)
        return ticker, df
    except Exception as e:
        return ticker, None

def plot_stock(ticker, df, tolerance):
    # Sadece bugünün (veya en son günün) verisini filtrele
    last_date = df.index[-1].date()
    df_plot = df[df.index.date == last_date]

    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(x=df_plot.index,
                open=df_plot['Open'],
                high=df_plot['High'],
                low=df_plot['Low'],
                close=df_plot['Close'],
                name='Fiyat Mumu'))

    # Keltner Upper
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Keltner_Upper'], 
                             line=dict(color='rgba(255, 0, 0, 0.5)', width=1), 
                             name='Keltner Üst'))
    
    # EMA
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA'], 
                             line=dict(color='rgba(255, 165, 0, 0.5)', width=1, dash='dash'), 
                             name='EMA (20)'))

    # Keltner Lower
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Keltner_Lower'], 
                             line=dict(color='rgba(0, 128, 0, 0.5)', width=1), 
                             name='Keltner Alt',
                             fill='tonexty', fillcolor='rgba(128, 128, 128, 0.1)'))
                             
    # GÜÇLÜ AL noktalarını tespit et (fiyat belirlenen toleransa veya daha altına düştüğünde)
    buy_signals = df_plot[((df_plot['Low'] - df_plot['Keltner_Lower']) / df_plot['Keltner_Lower'] * 100) <= tolerance]
    
    if not buy_signals.empty:
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] - (buy_signals['Low'] * 0.002), # Biraz altına yerleştir
                                 mode='markers+text',
                                 marker=dict(symbol='triangle-up', size=14, color='green'),
                                 text=['GÜÇLÜ AL'] * len(buy_signals),
                                 textposition='bottom center',
                                 textfont=dict(color='green', size=11, family='Arial Black'),
                                 name='Güçlü Al Sinyali'))

    # GÜÇLÜ SAT noktalarını tespit et (fiyat belirlenen toleransa veya daha üstüne çıktığında)
    sell_signals = df_plot[((df_plot['Keltner_Upper'] - df_plot['High']) / df_plot['Keltner_Upper'] * 100) <= tolerance]
    
    if not sell_signals.empty:
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] + (sell_signals['High'] * 0.002), # Biraz üstüne yerleştir
                                 mode='markers+text',
                                 marker=dict(symbol='triangle-down', size=14, color='red'),
                                 text=['GÜÇLÜ SAT'] * len(sell_signals),
                                 textposition='top center',
                                 textfont=dict(color='red', size=11, family='Arial Black'),
                                 name='Güçlü Sat Sinyali'))

    fig.update_layout(
        title=f"{ticker} - 5 Dakikalık Keltner Kanalı (Sadece {last_date} Tarihli Veriler)",
        yaxis_title="Fiyat (TL)",
        xaxis_title="Zaman",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=0, r=0, t=50, b=0)
    )
    
    return fig

def main():
    st.title("📈 Keltner Channel Hisse Tarama & Analiz")
    st.markdown("""
    Bu uygulama, girdiğiniz hisselerin 5 dakikalık (son 7 gün) verilerini çeker, 
    Keltner kanallarını hesaplar ve fiyat Keltner kanallarında sınır bölgelere belirlenen tolerans mesafesinde yakınsa (veya aştıysa) **Alım/Satım Sinyalleri** tablosunda gösterir.
    """)

    col1, col2 = st.columns([3, 1])
    with col1:
        user_input = st.text_input("Analiz edilecek hisse kodlarını girin (Örn: THYAO ASELS GARAN HEDEF ODINE):", value="THYAO ASELS GARAN HEDEF ODINE")
    with col2:
        tolerance = st.number_input("Tolerans (%) - Fiyat Alt banda ne kadar yakın olsun?", min_value=0.0, max_value=10.0, value=0.5, step=0.1)

    if st.button("Analizi Başlat", type="primary"):
        tickers = [t.strip().upper() for t in re.split(r'[,\s]+', user_input) if t.strip()]

        if not tickers:
            st.warning("Lütfen en az bir hisse kodu girin.")
            return

        st.info(f"Toplam {len(tickers)} hisse analiz ediliyor...")
        
        results = []
        graphs = []
        
        progress_bar = st.progress(0)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            fetched_data = list(executor.map(fetch_data, tickers))
            
        for i, (ticker, df) in enumerate(fetched_data):
            progress_bar.progress((i + 1) / len(tickers))
            
            if df is not None:
                # Grafiği hazırla
                graphs.append((ticker, plot_stock(ticker, df, tolerance)))
                
                # Sinyal kontrolü
                latest_row = df.iloc[-1]
                current_price = latest_row['Close']
                lower_band = latest_row['Keltner_Lower']
                upper_band = latest_row['Keltner_Upper']
                
                # Alım (Alt banda yakınlık) ve Satım (Üst banda yakınlık) uzaklıkları
                distance_buy_pct = (current_price - lower_band) / lower_band * 100
                distance_sell_pct = (upper_band - current_price) / upper_band * 100
                
                if distance_buy_pct <= tolerance:
                    results.append({
                        'Hisse': ticker,
                        'Sinyal': '🟢 GÜÇLÜ AL',
                        'Fiyat (TL)': round(current_price, 2),
                        'Hedef Band (TL)': round(lower_band, 2),
                        'Banda Uzaklık (%)': round(distance_buy_pct, 2)
                    })
                elif distance_sell_pct <= tolerance:
                    results.append({
                        'Hisse': ticker,
                        'Sinyal': '🔴 GÜÇLÜ SAT',
                        'Fiyat (TL)': round(current_price, 2),
                        'Hedef Band (TL)': round(upper_band, 2),
                        'Banda Uzaklık (%)': round(distance_sell_pct, 2)
                    })
            else:
                st.error(f"{ticker} verisi çekilemedi veya yetersiz (7 günlük 5D).")

        st.success("Analiz tamamlandı!")

        st.subheader("🎯 Mevcut Alım / Satım Sinyali Veren Hisseler")
        if results:
            results_df = pd.DataFrame(results)
            # Farka göre sırala (En az farka sahip olan -en sınırda olan- en üstte)
            results_df = results_df.sort_values(by='Banda Uzaklık (%)').reset_index(drop=True)
            st.dataframe(results_df, use_container_width=True)
        else:
            st.warning(f"Şu anki güncel fiyatlarda, Keltner bandlarına %{tolerance} yakınlığında bir hisse bulunamadı.")

        st.subheader("📊 Hisse Grafikleri")
        for ticker, fig in graphs:
            st.plotly_chart(fig, use_container_width=True)

if __name__ == '__main__':
    main()
