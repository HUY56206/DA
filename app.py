import json
import time
import urllib.request
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# Cau hinh trang
# ----------------------------------------------------------------------------
st.set_page_config(page_title="META Realtime Dashboard", layout="wide")

TICKERS = {
    "META": "Meta Platforms",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
}
LOOKBACK_DAYS = 365
REFRESH_SECONDS = 60


# ----------------------------------------------------------------------------
# Load du lieu tu Yahoo Finance (khong can API key)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_history(ticker: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Tai lich su OHLCV tu Yahoo Finance."""

    def _get(url: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)

    base = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range={d}d&interval=1d"
    try:
        data = _get(base.format(t=ticker, d=days))
    except Exception:
        data = _get(base.replace("query1", "query2").format(t=ticker, d=days))

    r = data["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(r["timestamp"], unit="s"),
            "Open": q["open"],
            "High": q["high"],
            "Low": q["low"],
            "Close": q["close"],
            "Volume": q["volume"],
        }
    ).dropna().reset_index(drop=True)
    return df


# ----------------------------------------------------------------------------
# Chi bao ky thuat
# ----------------------------------------------------------------------------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Return"] = df["Close"].pct_change() * 100
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["RSI"] = rsi(df["Close"], 14)

    mid = df["Close"].rolling(20).mean()
    std = df["Close"].rolling(20).std()
    df["BB_mid"] = mid
    df["BB_up"] = mid + 2 * std
    df["BB_low"] = mid - 2 * std

    df["Vol20"] = df["Return"].rolling(20).std() * np.sqrt(252)
    df["Drawdown"] = df["Close"] / df["Close"].cummax() - 1
    return df


def compute_metrics(df: pd.DataFrame) -> dict:
    last, prev = df.iloc[-1], df.iloc[-2]
    rets = df["Return"].dropna()
    vol_annual = rets.std() * np.sqrt(252)
    sharpe = (rets.mean() * 252) / vol_annual if vol_annual > 0 else np.nan
    cum_ret_1y = (last["Close"] / df.iloc[0]["Close"] - 1) * 100
    return {
        "price": last["Close"],
        "change": (last["Close"] / prev["Close"] - 1) * 100,
        "volume": last["Volume"],
        "avg_vol": df["Volume"].tail(20).mean(),
        "rsi": last["RSI"],
        "vol20": last["Vol20"],
        "sharpe": sharpe,
        "cumret": cum_ret_1y,
        "max_dd": df["Drawdown"].min() * 100,
        "range_high": last["High"],
        "range_low": last["Low"],
    }


# ----------------------------------------------------------------------------
# Bieu do Plotly
# ----------------------------------------------------------------------------
def overview_chart(df: pd.DataFrame, sma: bool = True) -> go.Figure:
    """Candlestick pro + SMA + volume + cham sang bien dong (dark theme)."""
    d = df.reset_index(drop=True)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.04)

    # 1) Candlestick: nen xanh (tang) / do (giam)
    fig.add_trace(go.Candlestick(
        x=d["Date"], open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
        name="Giá",
        increasing=dict(line=dict(color="#2ecc71", width=1), fillcolor="#2ecc71"),
        decreasing=dict(line=dict(color="#e74c3c", width=1), fillcolor="#e74c3c"),
        whiskerwidth=0.25,
    ), row=1, col=1)

    if sma:
        fig.add_trace(go.Scatter(x=d["Date"], y=d["SMA20"], name="SMA20",
                                 line=dict(color="#ffd54f", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=d["Date"], y=d["SMA50"], name="SMA50",
                                 line=dict(color="#7c9cff", width=1.5)), row=1, col=1)

    # 2) Cham sang boi toan diem gia moi nhat
    last = d.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["Date"]], y=[last["Close"]], mode="markers", name="Hôm nay",
        marker=dict(size=15, color="#ff6b6b",
                    line=dict(color="white", width=2)),
        hovertemplate="%{x|%d/%m} – đóng cửa: $%{y:.2f}<extra></extra>",
    ), row=1, col=1)

    # 3) Volume mau theo phien tang/giam
    vol_colors = np.where(d["Close"] >= d["Open"],
                          "rgba(46, 204, 113, 0.55)", "rgba(231, 76, 60, 0.55)")
    fig.add_trace(go.Bar(x=d["Date"], y=d["Volume"], name="Khối lượng",
                         marker_color=vol_colors), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", hovermode="x unified", height=600,
        margin=dict(t=40, b=20, l=40, r=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6EDF3"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=12)),
        xaxis_rangeslider_visible=False, uirevision="fixed",
    )
    fig.update_xaxes(showgrid=False,
                     rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(title_text="Giá (USD)", row=1, col=1,
                     gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(title_text="KL", row=2, col=1, showticklabels=False,
                     gridcolor="rgba(255,255,255,0.08)")
    return fig


def technical_chart(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.05)

    # Gia + Bollinger Bands (fill vung giua hai day)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"], name="Close",
                             line=dict(color="#7c9cff", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_up"], name="BB trên",
                             line=dict(color="rgba(255,255,255,0.35)",
                                       dash="dot", width=1)),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_low"], name="BB dưới",
                             line=dict(color="rgba(255,255,255,0.35)",
                                       dash="dot", width=1),
                             fill="tonexty",
                             fillcolor="rgba(124, 156, 255, 0.12)"),
                  row=1, col=1)

    # RSI + vung mua ban
    fig.add_trace(go.Scatter(x=df["Date"], y=df["RSI"], name="RSI",
                             line=dict(color="#c678dd", width=2),
                             fill="tozeroy",
                             fillcolor="rgba(198, 120, 221, 0.10)"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#e74c3c",
                  annotation_text="Quá mua", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#2ecc71",
                  annotation_text="Quá bán", row=2, col=1)

    # MACD + histogram
    fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD"], name="MACD",
                             line=dict(color="#7c9cff", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Signal"], name="Signal",
                             line=dict(color="#ffd54f", width=1.2)), row=3, col=1)
    fig.add_bar(x=df["Date"], y=np.where(df["MACD"] >= df["Signal"], df["MACD"], 0),
                name="Hist +", marker_color="#2ecc71", opacity=0.5, row=3, col=1)
    fig.add_bar(x=df["Date"], y=np.where(df["MACD"] < df["Signal"], df["MACD"], 0),
                name="Hist -", marker_color="#e74c3c", opacity=0.5, row=3, col=1)

    fig.update_layout(
        template="plotly_dark", hovermode="x unified", height=780,
        margin=dict(t=30, b=30, l=40, r=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6EDF3"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False,
                     rangebreaks=[dict(bounds=["sat", "mon"])])
    for r in (1, 2, 3):
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", row=r, col=1)
    fig.update_yaxes(title_text="Giá + BB", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    return fig


def correla_heatmap(tickers: list, days: int = 365) -> go.Figure:
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_history(t, days).set_index("Date")["Close"]
        except Exception:
            continue
    frame = pd.DataFrame(closes).pct_change().dropna()
    corr = frame.corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=list(corr.columns), y=list(corr.columns),
        colorscale="RdYlGn", zmin=-1, zmax=1,
        text=np.round(corr.values, 2), texttemplate="%{text}",
        textfont=dict(size=16),
        hovertemplate="%{x} ~ %{y}: %{z:.2f}<extra></extra>",
        colorbar=dict(title="r", thickness=14, outlinewidth=0),
    ))
    fig.update_layout(
        template="plotly_dark", height=540,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6EDF3"),
        title=dict(text="Ma trận tương quan lợi suất hàng ngày",
                   x=0.02, font=dict(size=18)),
        margin=dict(t=60, b=40, l=40, r=30),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


# ----------------------------------------------------------------------------
# Giao dien
# ----------------------------------------------------------------------------
ticker = st.sidebar.selectbox("Cổ phiếu", options=list(TICKERS),
                              format_func=lambda t: f"{t} - {TICKERS[t]}")
days = st.sidebar.slider("Tổng số ngày dữ liệu", 180, 730, 365, 30)
view_days = st.sidebar.slider("Số ngày hiển thị trên biểu đồ", 30, 365, 180, 15)
if view_days > days:
    view_days = days
show_sma = st.sidebar.checkbox("Hiển thị SMA 20/50", value=True)

st_autorefresh(interval=REFRESH_SECONDS * 1000, key="realtime")

now = dt.datetime.now()
st.title("Dashboard Real-time – Tự động cập nhật dữ liệu")
st.caption(
    f"Lần cập nhật cuối: {now.strftime('%H:%M:%S')} "
    "(tự động mỗi phút) | Nguồn: Yahoo Finance"
)

df = fetch_history(ticker, days)
if df.empty:
    st.error("Không lấy được dữ liệu. Vui lòng thử lại sau giây lát.")
    st.stop()

df = add_indicators(df)
m = compute_metrics(df)

# ----------------------------------------------------------------------------
# Metrix realtime
# ----------------------------------------------------------------------------
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Giá hiện tại", f"${m['price']:.2f}", f"{m['change']:+.2f}%")
c2.metric("RSI (14)", f"{m['rsi']:.1f}")
c3.metric("Độ biến động 20p", f"{m['vol20'] * 100:.1f}%/năm")
c4.metric("Lợi suất 1 năm", f"{m['cumret']:+.1f}%")
c5.metric("Sharpe (ngày)", f"{m['sharpe']:.2f}" if not np.isnan(m['sharpe']) else "-")
c6.metric("Max Drawdown", f"{m['max_dd']:.1f}%")

tab_overview, tab_tech, tab_corr = st.tabs(
    ["Tổng quan", "Phân tích kỹ thuật", "Tương quan danh mục"]
)

with tab_overview:
    st.plotly_chart(overview_chart(df.tail(view_days), show_sma), width="stretch")
    s1, s2, s3 = st.columns(3)
    s1.metric("Khối lượng (hôm nay)", f"{m['volume']:,.0f}")
    s2.metric("Khối lượng TB 20p", f"{m['avg_vol']:,.0f}")
    s3.metric("Cao/Thấp hôm nay",
              f"${m['range_high']:.2f} / ${m['range_low']:.2f}")
    st.caption(
        "Trang tự động refresh mỗi phút và lấy lại dữ liệu mới từ Yahoo Finance "
        "(với phiên mới nhất khi có sẵn, thông thường 1 lần/ngày)."
    )

with tab_tech:
    st.plotly_chart(technical_chart(df), width="stretch")
    st.markdown(
        """
        **Giải thích chỉ báo (khái niệm khoa học):**
        - **RSI (Relative Strength Index)**: đo lực mua/bán. >70 quá mua, <30 quá bán.
        - **MACD (Moving Average Convergence Divergence)**: hiệu EMA12 và EMA26.
          Khi MACD cắt lên Signal = tín hiệu tăng, cắt xuống = tín hiệu giảm.
        - **Bollinger Bands**: SMA20 ± 2×std(20). Giá chạm dải trên (dưới) thường
          bị co kéo trở lại vùng giữa (revert to the mean).
        """
    )

with tab_corr:
    watchlist = st.multiselect(
        "Chọn danh mục để so sánh", list(TICKERS),
        default=["META", "AAPL", "NVDA", "GOOGL", "TSLA"],
    )
    if len(watchlist) >= 2:
        st.plotly_chart(correla_heatmap(watchlist, days), width="stretch")
        st.caption(
            "Heatmap tương quan lợi suất hàng ngày giữa các cổ phiếu – "
            "hệ số gần 1: đi cùng nhau, gần -1: ngược chiều."
        )
    else:
        st.info("Chọn ít nhất 2 cổ phiếu để xem ma trận tương quan.")

st.divider()
st.caption("Đồ án môn PTDLNC – Kỹ thuật Real-Time Updates (Streamlit + Yahoo Finance).")