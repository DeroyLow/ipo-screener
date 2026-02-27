from typing import Iterable, List, Tuple, Dict, Any

import pandas as pd


def _is_na_scalar(value: Any) -> bool:
  """
  Safely determine whether a value should be treated as NA/invalid.

  Handles both plain Python scalars and pandas objects (Series/Index),
  always returning a single boolean so it can be used inside an `if`
  statement without raising "truth value of a Series is ambiguous".
  """
  result = pd.isna(value)
  if isinstance(result, (pd.Series, pd.Index)):
    # If we somehow get a vector back, treat it as NA if *all* entries are NA.
    return bool(result.all())
  return bool(result)


def _to_scalar(value: Any) -> float | int | None:
  """
  Coerce a pandas object or plain value down to a single numeric scalar.

  This is defensive against cases where a cell may unexpectedly contain a
  Series/Index; we always reduce to one representative value (last element),
  or return None if that is not possible.
  """
  if _is_na_scalar(value):
    return None

  # If we somehow get a vector-like object, reduce it to a single element.
  if isinstance(value, (pd.Series, pd.Index)):
    if value.size == 0:
      return None
    # Prefer the last value, which matches how we typically look at "latest".
    scalar = value.iloc[-1] if hasattr(value, "iloc") else value[-1]
    if _is_na_scalar(scalar):
      return None
    try:
      return float(scalar)
    except (TypeError, ValueError):
      return None

  # Plain python scalar or numpy scalar.
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def calculate_moving_averages(
  df: pd.DataFrame,
  windows: Iterable[int] = (10, 20, 50, 100, 200),
) -> pd.DataFrame:
  """
  Add simple moving average (SMA) columns to the price DataFrame.

  Only yields meaningful values once there are enough data points; earlier rows
  will naturally be NaN. Column names are of the form 'SMA_<window>'.
  """
  if df is None or df.empty:
    return df

  closes = df.get("Close")
  if closes is None:
    return df

  for window in windows:
    if window <= 0:
      continue
    col = f"SMA_{window}"
    if len(df) >= window:
      df[col] = closes.rolling(window=window, min_periods=window).mean()
    else:
      # Not enough history; create the column but fill with NA so the UI can
      # render "N/A" for this MA.
      df[col] = pd.NA

  return df


def get_ma_signals(
  df: pd.DataFrame, windows: Iterable[int] = (10, 20, 50, 100, 200)
) -> Tuple[Dict[int, str], pd.Series]:
  """
  Determine whether the latest close is above/below each moving average.

  Returns:
      signals: {window: 'above' | 'below' | 'n/a'}
      latest_row: the last row of the DataFrame (for convenient access to values)
  """
  signals: Dict[int, str] = {}

  if df is None or df.empty:
    return signals, pd.Series(dtype="float64")

  latest = df.iloc[-1]
  close = latest.get("Close")

  for window in windows:
    col = f"SMA_{window}"
    ma_value = latest.get(col)
    close_scalar = _to_scalar(close)
    ma_scalar = _to_scalar(ma_value)

    if close_scalar is None or ma_scalar is None:
      signals[window] = "n/a"
    else:
      signals[window] = "above" if close_scalar > ma_scalar else "below"

  return signals, latest


