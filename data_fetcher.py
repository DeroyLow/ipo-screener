import datetime as dt
from typing import Optional

import pandas as pd
import yfinance as yf

try:
  import finnhub  # type: ignore
except ImportError:  # pragma: no cover - optional dependency at runtime
  finnhub = None


def get_recent_ipos(days_back: int = 90, api_key: Optional[str] = None) -> pd.DataFrame:
  """
  Fetch a list of recent IPOs.

  If a Finnhub API key is provided and finnhub-python is installed, use the
  official IPO calendar. Otherwise, fall back to a small hard-coded list of
  recent US IPOs so the app still works in demo mode.
  """
  today = dt.date.today()
  start = today - dt.timedelta(days=days_back)

  records = []

  if api_key and finnhub is not None:
    try:
      client = finnhub.Client(api_key=api_key)
      raw = client.ipo_calendar(_from=start.isoformat(), to=today.isoformat())
      calendar = raw.get("ipoCalendar", []) or []

      for row in calendar:
        # Finnhub fields: symbol, name, exchange, date, numberOfShares, price, status
        symbol = row.get("symbol")
        if not symbol:
          continue

        exchange = (row.get("exchange") or "").upper()
        # Keep US‑listed exchanges only
        if not any(x in exchange for x in ("NASDAQ", "NYSE", "AMEX", "BATS")):
          continue

        ipo_date = pd.to_datetime(row.get("date")).date() if row.get("date") else None
        records.append(
          {
            "ticker": symbol.upper(),
            "company": row.get("name") or symbol.upper(),
            "exchange": exchange,
            "ipo_date": ipo_date,
          }
        )
    except Exception:
      # If Finnhub fails for any reason, fall back to the demo list below.
      records = []

  if not records:
    # Demo fallback: a small, realistic‑looking set of recent US IPOs.
    demo_data = [
      {"ticker": "ARM", "company": "Arm Holdings plc", "exchange": "NASDAQ", "ipo_date": today - dt.timedelta(days=160)},
      {"ticker": "KVYO", "company": "Klaviyo Inc.", "exchange": "NYSE", "ipo_date": today - dt.timedelta(days=140)},
      {"ticker": "CART", "company": "Maplebear Inc. (Instacart)", "exchange": "NASDAQ", "ipo_date": today - dt.timedelta(days=135)},
      {"ticker": "BIRK", "company": "Birkenstock Holding plc", "exchange": "NYSE", "ipo_date": today - dt.timedelta(days=130)},
      {"ticker": "SEMR", "company": "Semrush Holdings, Inc.", "exchange": "NYSE", "ipo_date": today - dt.timedelta(days=320)},
      {"ticker": "NUVL", "company": "Nuvalent, Inc.", "exchange": "NASDAQ", "ipo_date": today - dt.timedelta(days=280)},
    ]
    records = demo_data

  df = pd.DataFrame(records)
  if "ipo_date" in df.columns:
    df["ipo_date"] = pd.to_datetime(df["ipo_date"]).dt.date

  # Drop duplicates by ticker, keep the most recent IPO date if any.
  if not df.empty:
    df = df.sort_values("ipo_date").drop_duplicates(subset=["ticker"], keep="last")

  return df.reset_index(drop=True)


def get_price_data(ticker: str, period: str = "6mo") -> pd.DataFrame:
  """
  Fetch daily OHLCV price data for a given ticker using yfinance.
  """
  if not ticker:
    return pd.DataFrame()

  df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
  if df.empty:
    return df

  df = df.rename(
    columns={
      "Open": "Open",
      "High": "High",
      "Low": "Low",
      "Close": "Close",
      "Adj Close": "AdjClose",
      "Volume": "Volume",
    }
  )
  df.index = pd.to_datetime(df.index)
  df.sort_index(inplace=True)
  return df


def get_stock_info(ticker: str) -> dict:
  """
  Fetch basic stock info (sector, market cap, etc.) via yfinance.
  """
  info: dict = {}
  if not ticker:
    return info

  try:
    y_ticker = yf.Ticker(ticker)
    try:
      info = y_ticker.info or {}
    except Exception:
      # Newer yfinance versions may deprecate .info; fall back to fast_info where possible.
      fast = getattr(y_ticker, "fast_info", None)
      if fast is not None:
        info = fast.__dict__.get("_fast_info", {})
  except Exception:
    info = {}

  return info or {}


