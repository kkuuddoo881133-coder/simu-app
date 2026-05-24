from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


Direction = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class StrategySignal:
    index: int
    time: pd.Timestamp
    direction: Direction
    entry: float
    reason: str
    sl: float | None = None
    tp: float | None = None


def ensure_ohlc(df: pd.DataFrame) -> None:
    missing = {"Datetime", "Open", "High", "Low", "Close"} - set(df.columns)
    if missing:
        raise ValueError(f"OHLC列が不足しています: {sorted(missing)}")
