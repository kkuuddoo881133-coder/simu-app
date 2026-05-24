from __future__ import annotations

import pandas as pd

from strategies.base import StrategySignal, ensure_ohlc


DISPLAY_NAME = "三尊 / 逆三尊"


def find_signals(
    df: pd.DataFrame,
    pivot_window: int = 5,
    shoulder_tolerance_pips: float = 15.0,
    min_head_gap_pips: float = 10.0,
    trade_side: str = "both",
) -> list[StrategySignal]:
    ensure_ohlc(df)
    signals: list[StrategySignal] = []
    pip = 0.01
    highs = _pivot_highs(df, pivot_window)
    lows = _pivot_lows(df, pivot_window)

    if trade_side in {"both", "sell"}:
        for left, head, right in zip(highs, highs[1:], highs[2:]):
            left_price = df.iloc[left].High
            head_price = df.iloc[head].High
            right_price = df.iloc[right].High
            shoulders_close = abs(left_price - right_price) <= shoulder_tolerance_pips * pip
            head_above = head_price - max(left_price, right_price) >= min_head_gap_pips * pip
            if shoulders_close and head_above and right + 1 < len(df):
                row = df.iloc[right + 1]
                signals.append(
                    StrategySignal(
                        index=right + 1,
                        time=row.Datetime,
                        direction="SELL",
                        entry=float(row.Open),
                        reason="head_and_shoulders",
                    )
                )

    if trade_side in {"both", "buy"}:
        for left, head, right in zip(lows, lows[1:], lows[2:]):
            left_price = df.iloc[left].Low
            head_price = df.iloc[head].Low
            right_price = df.iloc[right].Low
            shoulders_close = abs(left_price - right_price) <= shoulder_tolerance_pips * pip
            head_below = min(left_price, right_price) - head_price >= min_head_gap_pips * pip
            if shoulders_close and head_below and right + 1 < len(df):
                row = df.iloc[right + 1]
                signals.append(
                    StrategySignal(
                        index=right + 1,
                        time=row.Datetime,
                        direction="BUY",
                        entry=float(row.Open),
                        reason="inverse_head_and_shoulders",
                    )
                )

    return sorted(signals, key=lambda signal: signal.index)


def _pivot_highs(df: pd.DataFrame, window: int) -> list[int]:
    points = []
    for i in range(window, len(df) - window):
        current = df.iloc[i].High
        neighborhood = df.iloc[i - window : i + window + 1].High
        if current == neighborhood.max():
            points.append(i)
    return points


def _pivot_lows(df: pd.DataFrame, window: int) -> list[int]:
    points = []
    for i in range(window, len(df) - window):
        current = df.iloc[i].Low
        neighborhood = df.iloc[i - window : i + window + 1].Low
        if current == neighborhood.min():
            points.append(i)
    return points

