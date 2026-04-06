"""Transformações em pandas para gráficos e KPIs derivados."""

from __future__ import annotations

from typing import Optional

import pandas as pd


def add_rolling_mean(
    df: pd.DataFrame,
    value_col: str,
    date_col: str = "day",
    window: int = 7,
    out_col: str | None = None,
) -> pd.DataFrame:
    """
    Adiciona média móvel sobre série ordenada por data.

    ``window``: dias úteis na série (linha temporal pode ter falhas).
    """
    if df.empty or value_col not in df.columns:
        return df
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col]).sort_values(date_col)
    oc = out_col or f"{value_col}_ma{window}"
    out[oc] = out[value_col].rolling(window=min(window, len(out)), min_periods=1).mean()
    return out


def kpi_delta_pct(current: float, previous: float) -> Optional[float]:
    """Variação percentual; ``None`` se período anterior é zero."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100.0


def format_delta_pct(d: Optional[float]) -> Optional[str]:
    """Rótulo para ``st.metric``."""
    if d is None:
        return None
    return f"{d:+.1f}% vs período ant."
