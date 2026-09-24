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
# Chi bao ky thuat (dung luong khoa hoc)
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

    df["Vol20"] = df["Return"].rolling(20).std() * np.sqrt(252)  # do bien dong nam
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
    """Bieu do chinh (area line + marker mau theo loi suat) + volume."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.04)

    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Close"], mode="lines", name="Close",
        line=dict(color="rgba(70, 130, 220, 0.9)", width=2),
        fill="tozeroy", fillcolor="rgba(70, 130, 220, 0.12)",
    ), row=1, col=1)

    if sma:
        for col, color, name in (("SMA20", "#ffd54f", "SMA20"),
                                 ("SMA50", "#9e9ef0", "SMA50")):
            fig.add_trace(go.Scatter(x=df["Date"], y=df[col], name=name,
                                     line=dict(color=color, width=1.2)),
                          row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Close"], mode="markers", name="Return",
        marker=dict(size=9, color=df["Return"].fillna(0), colorscale="RdYlGn",
                    cmin=-4, cmax=4, line=dict(color="white", width=0.6),
                    showscale=True, colorbar=dict(title="Daily return %")),
    ), row=1, col=1)

    vol_colors = np.where(df["Close"] >= df["Open"], "#26a69a", "#ef5350")
    fig.add_trace(go.Bar(x=df["Date"], y=df["Volume"], name="Volume",
                         marker_color=vol_colors, opacity=0.7),
                  row=2, col=1)

    fig.update_layout(
        template="plotly_white", hovermode="x unified", height=560,
        margin=dict(t=30, b=30, l=50, r=60), showlegend=True,
    )
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1,
                     showticklabels=False)
    return fig


def technical_chart(df: pd.DataFrame) -> go.Figure:
    """Bieu do phan tich ky thuat: gia + BB, RSI, MACD."""
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.05)

    fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"], name="Close",
                             line=dict(color="#2c3e50", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_up"], name="BB upper",
                             line=dict(color="gray", dash="dot", width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_low"], name="BB lower",
                             line=dict(color="gray", dash="dot", width=1)),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_mid"], name="BB mid (SMA20)",
                             line=dict(color="#ffd54f", width=1.2)), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["Date"], y=df["RSI"], name="RSI",
                             line=dict(color="#9b59b6", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD"], name="MACD",
                             line=dict(color="blue", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Signal"], name="Signal",
                             line=dict(color="orange", width=1.2)), row=3, col=1)
    fig.add_bar(x=df["Date"], y=np.where(df["MACD"] >= df["Signal"], df["MACD"], 0),
                name="Hist +", marker_color="#26a69a", opacity=0.4, row=3, col=1)
    fig.add_bar(x=df["Date"], y=np.where(df["MACD"] < df["Signal"], df["MACD"], 0),
                name="Hist -", marker_color="#ef5350", opacity=0.4, row=3, col=1)

    fig.update_layout(template="plotly_white", hovermode="x unified",
                      height=760, margin=dict(t=30, b=30, l=50, r=20))
    fig.update_yaxes(title_text="Price", row=1, col=1, range=[None, None])
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
        colorscale="RdBu_r", zmin=-1, zmax=1,
        text=np.round(corr.values, 2), texttemplate="%{text}",
        hovertemplate="%{x} ~ %{y}: %{z:.2f}<extra></extra>",
    ))
    fig.update_layout(template="plotly_white", height=520,
                      title="Ma tran tuong quan loi suat hang ngay",
                      margin=dict(t=60, b=40, l=40, r=30))
    return fig


# ----------------------------------------------------------------------------
# Giao dien
# ----------------------------------------------------------------------------
ticker = st.sidebar.selectbox("Co phieu", options=list(TICKERS),
                              format_func=lambda t: f"{t} - {TICKERS[t]}")
interval = st.sidebar.slider("Tan suat cap nhat (giay)", 5, 120, 30, 5)
days = st.sidebar.slider("So ngay du lieu", 180, 730, 365, 30)
show_sma = st.sidebar.checkbox("Hien thi SMA 20/50", value=True)

# ============ REAL-TIME UPDATES: tu dong chay lai app moi interval ============
st_autorefresh(interval=interval * 1000, key="realtime")

st.title("Meta Platforms (META) - Realtime Dashboard")
st.caption(
    f"Cap nhat luc {dt.datetime.now().strftime('%H:%M:%S')} "
    f"| cu {interval}s moi lan | nguon: Yahoo Finance"
)

try:
    df = fetch_history(ticker, days)
    if df.empty:
        st.error("Khong lay duoc du lieu. Vui long thu lai sau giay lat.")
        st.stop()
except Exception as exc:
    st.error(f"Loi tai du lieu: {exc}")
    st.stop()

df = add_indicators(df)
m = compute_metrics(df)

# ---- Metrix (real-time) ----
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Gia hien tai", f"${m['price']:.2f}", f"{m['change']:+.2f}%")
c2.metric("RSI (14)", f"{m['rsi']:.1f}")
c3.metric("Do bien dong 20p", f"{m['vol20'] * 100:.1f}%/nam")
c4.metric("Loi suat 1 nam", f"{m['cumret']:+.1f}%")
c5.metric("Sharpe (ngay)", f"{m['sharpe']:.2f}" if not np.isnan(m['sharpe']) else "-")
c6.metric("Max Drawdown", f"{m['max_dd']:.1f}%")

tab_overview, tab_tech, tab_corr = st.tabs(
    ["Tong quan", "Phan tich ky thuat", "Tuong quan danh muc"]
)

with tab_overview:
    st.plotly_chart(overview_chart(df, show_sma), width="stretch")
    s1, s2, s3 = st.columns(3)
    s1.metric("Khoi luong (hom nay)", f"{m['volume']:,.0f}")
    s2.metric("Khoi luong TB 20p", f"{m['avg_vol']:,.0f}")
    s3.metric("Cao/Thap hom nay",
              f"${m['range_high']:.2f} / ${m['range_low']:.2f}")

with tab_tech:
    st.plotly_chart(technical_chart(df), width="stretch")
    st.markdown(
        """
        **Giai thich chi bao (khai niem khoa hoc):**
        - **RSI (Relative Strength Index)**: do luc mua/ban. >70 qua mua, <30 qua ban.
        - **MACD (Moving Average Convergence Divergence)**: hieu EMA12 va EMA26.
          Khi MACD cat len Signal = tin hieu tang, cat xuong = tin hieu giam.
        - **Bollinger Bands**: SMA20 +/- 2*std(20). Gia cham day tren (duoi) thuong
          bi co lai (revert to the mean).
        """
    )

with tab_corr:
    watchlist = st.multiselect(
        "Chon danh muc de so sanh", list(TICKERS),
        default=["META", "AAPL", "NVDA", "GOOGL", "TSLA"],
    )
    if len(watchlist) >= 2:
        st.plotly_chart(correla_heatmap(watchlist, days), width="stretch")
        st.caption(
            "Heatmap tuong quan loi suat hang ngay giua cac co phieu - "
            "he so gan 1: di cung nhau, gan -1: nguoc chieu."
        )
    else:
        st.info("Chon it nhat 2 co phieu de xem ma tran tuong quan.")

st.divider()
st.caption("Do an mon PTDLNC - Ky thuat Real-Time Updates (Streamlit + Yahoo Finance).")