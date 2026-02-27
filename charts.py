from typing import Iterable, List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


MA_COLORS = {
  10: "#22c55e",   # green
  20: "#0ea5e9",   # sky blue
  50: "#a855f7",   # purple
  100: "#f97316",  # orange
  200: "#e11d48",  # rose
}


def create_candlestick_chart(
  df: pd.DataFrame,
  ticker: str,
  ma_windows: Iterable[int] = (10, 20, 50, 100, 200),
) -> go.Figure:
  """
  Build a Plotly candlestick chart with MA overlays and a volume subplot.
  """
  if df is None or df.empty:
    fig = go.Figure()
    fig.update_layout(
      template="plotly_dark",
      title=f"{ticker} – no price data available",
      paper_bgcolor="#020617",
      plot_bgcolor="#020617",
      font=dict(color="#e5e7eb"),
    )
    return fig

  df = df.copy()
  df.index = pd.to_datetime(df.index)

  fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.03,
    row_heights=[0.7, 0.3],
  )

  # Main candlestick trace
  fig.add_trace(
    go.Candlestick(
      x=df.index,
      open=df["Open"],
      high=df["High"],
      low=df["Low"],
      close=df["Close"],
      name="Price",
      increasing_line_color="#22c55e",
      decreasing_line_color="#ef4444",
      increasing_fillcolor="#22c55e",
      decreasing_fillcolor="#ef4444",
      showlegend=False,
    ),
    row=1,
    col=1,
  )

  # Overlay a clear close-price line so the underlying price path is easy to see
  # alongside the moving averages and candles. We only check that the column
  # exists; Plotly will gracefully handle any NaNs in the data.
  if "Close" in df.columns:
    fig.add_trace(
      go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        name="Close price",
        line=dict(color="#e5e7eb", width=1.4),
        opacity=0.9,
      ),
      row=1,
      col=1,
    )

  # Moving average overlays
  for window in ma_windows:
    col = f"SMA_{window}"
    if col in df.columns and df[col].notna().any():
      fig.add_trace(
        go.Scatter(
          x=df.index,
          y=df[col],
          mode="lines",
          name=f"SMA {window}",
          line=dict(
            width=1.4,
            color=MA_COLORS.get(window, "#64748b"),
          ),
        ),
        row=1,
        col=1,
      )

  # Volume bars
  volume_colors = [
    "#22c55e" if c >= o else "#ef4444" for o, c in zip(df["Open"], df["Close"])
  ]

  fig.add_trace(
    go.Bar(
      x=df.index,
      y=df["Volume"],
      name="Volume",
      marker_color=volume_colors,
      opacity=0.6,
    ),
    row=2,
    col=1,
  )

  fig.update_layout(
    title=f"{ticker} – Candlestick with Moving Averages",
    template="plotly_dark",
    paper_bgcolor="#020617",  # slate‑950
    plot_bgcolor="#020617",
    margin=dict(l=40, r=40, t=40, b=40),
    hovermode="x unified",
    legend=dict(
      orientation="h",
      yanchor="bottom",
      y=1.02,
      xanchor="right",
      x=1,
      font=dict(size=11),
    ),
    xaxis_rangeslider_visible=False,
  )

  fig.update_xaxes(
    showgrid=True,
    gridcolor="rgba(148, 163, 184, 0.15)",
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    spikethickness=1,
    spikecolor="rgba(248, 250, 252, 0.9)",
  )

  fig.update_yaxes(
    showgrid=True,
    gridcolor="rgba(148, 163, 184, 0.15)",
    zerolinecolor="rgba(148, 163, 184, 0.25)",
  )

  return fig


