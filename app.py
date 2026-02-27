import datetime as dt
from typing import List

import pandas as pd
import streamlit as st

from data_fetcher import get_recent_ipos, get_price_data, get_stock_info
from indicators import calculate_moving_averages, get_ma_signals, _to_scalar
from charts import create_candlestick_chart


st.set_page_config(
  page_title="US IPO Screener – Technical Dashboard",
  layout="wide",
)


@st.cache_data(show_spinner=False)
def load_ipos(days_back: int, api_key: str | None) -> pd.DataFrame:
  return get_recent_ipos(days_back=days_back, api_key=api_key or None)


@st.cache_data(show_spinner=False)
def load_stock_info(ticker: str) -> dict:
  return get_stock_info(ticker)


@st.cache_data(show_spinner=False)
def load_price_data(ticker: str, period: str) -> pd.DataFrame:
  return get_price_data(ticker, period=period)


def format_market_cap(value: float | int | None) -> str:
  if value is None or pd.isna(value):
    return "N/A"
  v = float(value)
  if v >= 1e9:
    return f"${v/1e9:,.1f}B"
  if v >= 1e6:
    return f"${v/1e6:,.1f}M"
  return f"${v:,.0f}"


def main() -> None:
  # --- Sidebar controls ----------------------------------------------------
  with st.sidebar:
    st.markdown("### US IPO Screener")
    st.markdown(
      "[Get a free Finnhub API key](https://finnhub.io/register) "
      "to pull the live IPO calendar, or leave blank to use demo IPOs."
    )

    # If a Finnhub key is defined in Streamlit secrets (recommended for
    # Streamlit Cloud), use it as the default so the app "just works"
    # without typing the key every time.
    default_api_key = st.secrets.get("FINNHUB_API_KEY", "")

    api_key = st.text_input(
      "Finnhub API key (optional)",
      type="password",
      value=default_api_key,
    )

    lookback_days = st.slider(
      "IPO lookback window (days)",
      min_value=30,
      max_value=365,
      value=365,
      step=15,
    )

    ma_options = [10, 20, 50, 100, 200]
    selected_mas: List[int] = st.multiselect(
      "Moving averages",
      options=ma_options,
      default=[10, 20, 50],
    )

    manual_tickers = st.text_input(
      "Manual tickers (comma‑separated)",
      help="Add additional symbols not found in the IPO calendar.",
    )

    timeframe = st.selectbox(
      "Chart timeframe",
      options=["1mo", "3mo", "6mo", "1y"],
      index=2,
    )

  st.title("US IPO Screener – Technical Trader Dashboard")

  # --- Data loading --------------------------------------------------------
  effective_api_key = api_key.strip() or default_api_key or None
  ipos_df = load_ipos(lookback_days, effective_api_key)

  # Attach manual tickers with unknown IPO date (treated as recent).
  manual_list: List[str] = []
  if manual_tickers.strip():
    manual_list = [t.strip().upper() for t in manual_tickers.split(",") if t.strip()]
    for t in manual_list:
      if ipos_df.empty or t not in ipos_df["ticker"].values:
        ipos_df = pd.concat(
          [
            ipos_df,
            pd.DataFrame(
              [
                {
                  "ticker": t,
                  "company": t,
                  "exchange": "",
                  "ipo_date": dt.date.today(),
                }
              ]
            ),
          ],
          ignore_index=True,
        )

  if ipos_df.empty:
    st.warning("No IPOs found for the selected window.")
    return

  # --- Screener table construction ----------------------------------------
  period_map = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y"}
  period = period_map.get(timeframe, "6mo")

  rows = []
  today = dt.date.today()

  tickers = sorted(ipos_df["ticker"].unique())
  progress = st.progress(0.0, text="Loading price data and indicators...")

  for idx, ticker in enumerate(tickers, start=1):
    price_df = load_price_data(ticker, period=period)
    if price_df.empty:
      continue

    price_df = calculate_moving_averages(
      price_df, windows=selected_mas or ma_options
    )
    signals, latest = get_ma_signals(
      price_df, windows=selected_mas or ma_options
    )

    # Coerce potentially messy pandas objects down to clean numeric scalars
    # before using them in boolean checks or arithmetic.
    first_close = _to_scalar(price_df["Close"].iloc[0])
    last_close = _to_scalar(latest.get("Close"))
    volume = latest.get("Volume")

    base_row = ipos_df[ipos_df["ticker"] == ticker].iloc[-1]
    ipo_date = base_row.get("ipo_date")
    days_since_ipo = (today - ipo_date).days if isinstance(ipo_date, dt.date) else None

    info = load_stock_info(ticker)
    sector = info.get("sector") or info.get("industry") or ""
    market_cap = info.get("marketCap") or info.get("market_cap")

    change_pct = None
    if first_close is not None and last_close is not None and first_close != 0:
      change_pct = (last_close / first_close - 1.0) * 100.0

    row = {
      "Ticker": ticker,
      "Company": base_row.get("company", ticker),
      "IPO Date": ipo_date,
      "Days Since IPO": days_since_ipo,
      "Sector": sector,
      "Exchange": base_row.get("exchange", ""),
      "Current Price": float(last_close) if last_close is not None else None,
      "Change % (since IPO data window start)": change_pct,
      "Volume": float(volume) if volume is not None else None,
      "Market Cap": market_cap,
    }

    for window in selected_mas or ma_options:
      col = f"SMA_{window}"
      sma_val = latest.get(col)
      vs_pct = None
      sma_scalar = _to_scalar(sma_val)
      if sma_scalar is not None and last_close is not None:
        vs_pct = (last_close / sma_scalar - 1.0) * 100.0

      row[f"Price vs SMA {window} %"] = vs_pct
      row[f"Price vs SMA {window} status"] = signals.get(window, "n/a")

    rows.append(row)

    progress.progress(idx / len(tickers), text=f"Loaded {idx}/{len(tickers)} tickers")

  progress.empty()

  if not rows:
    st.warning("No price data available for the IPO list.")
    return

  screener_df = pd.DataFrame(rows)

  # Add a simple serial-number column for easier scanning in the table.
  screener_df.insert(0, "S/N", range(1, len(screener_df) + 1))

  # --- Styling helpers -----------------------------------------------------
  def ma_color(val: float | None) -> str:
    if val is None or pd.isna(val):
      return "background-color: rgba(15,23,42,0.9); color: #9ca3af;"
    if val > 0:
      return "background-color: rgba(22,163,74,0.25); color: #bbf7d0;"
    if val < 0:
      return "background-color: rgba(220,38,38,0.25); color: #fecaca;"
    return "background-color: rgba(15,23,42,0.9); color: #e5e7eb;"

  ma_cols = [c for c in screener_df.columns if "Price vs SMA" in c and "%" in c]
  display_df = screener_df.copy()

  styled = display_df.style.format(
    {
      "Current Price": "{:,.2f}",
      "Change % (since IPO data window start)": "{:+.2f}%",
      "Volume": "{:,.0f}",
      "Market Cap": lambda v: format_market_cap(v),
      **{col: "{:+.2f}%" for col in ma_cols},
    }
  ).applymap(ma_color, subset=ma_cols)

  st.subheader("IPO Screener")
  st.dataframe(styled, use_container_width=True, hide_index=True)

  # --- Ticker selection & chart -------------------------------------------
  st.subheader("Chart View")

  selected_ticker = st.selectbox(
    "Select ticker to view detailed chart",
    options=[r["Ticker"] for r in rows],
  )

  if selected_ticker:
    price_df = load_price_data(selected_ticker, period=period)
    price_df = calculate_moving_averages(price_df, windows=selected_mas or ma_options)

    fig = create_candlestick_chart(
      price_df,
      ticker=selected_ticker,
      ma_windows=selected_mas or ma_options,
    )

    latest_signals, latest_row = get_ma_signals(
      price_df, windows=selected_mas or ma_options
    )

    col_left, col_mid, col_right = st.columns([2, 3, 2])

    with col_left:
      st.markdown("**Key Stats**")
      info = load_stock_info(selected_ticker)

      # Sector / industry
      sector = info.get("sector") or info.get("industry") or "N/A"
      st.write(f"**Sector:** {sector}")

      # Market cap (support both .info and fast_info style keys)
      mc_raw = info.get("marketCap") or info.get("market_cap")
      st.write(f"**Market Cap:** {format_market_cap(mc_raw)}")

      # 52‑week range – try several common key names from yfinance
      low_52 = (
        info.get("fiftyTwoWeekLow")
        or info.get("fifty_two_week_low")
        or info.get("yearLow")
      )
      high_52 = (
        info.get("fiftyTwoWeekHigh")
        or info.get("fifty_two_week_high")
        or info.get("yearHigh")
      )
      low_52_disp = low_52 if low_52 is not None else "N/A"
      high_52_disp = high_52 if high_52 is not None else "N/A"
      st.write(f"**52‑week range:** {low_52_disp} – {high_52_disp}")

    with col_mid:
      st.plotly_chart(fig, use_container_width=True)

    with col_right:
      st.markdown("**MA Signals (latest close)**")
      for window, status in latest_signals.items():
        if status == "above":
          label = "Above"
          color = "🟢"
        elif status == "below":
          label = "Below"
          color = "🔴"
        else:
          label = "N/A"
          color = "⚪"
        st.write(f"{color} Price {label} SMA {window}")


if __name__ == "__main__":
  main()

