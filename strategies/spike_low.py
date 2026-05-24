from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import StrategySignal, ensure_ohlc


DISPLAY_NAME = "Spike"


def find_signals(
    df: pd.DataFrame,
    atr_period: int = 14,
    atr_multiplier: float = 1.0,
    max_body_ratio: float = 0.25,
    lookback: int = 20,
    atr_buffer: float = 0.2,
    risk_reward: float = 2.0,
    trade_side: str = "both",
) -> list[StrategySignal]:
    ensure_ohlc(df)
    signals: list[StrategySignal] = []

    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=atr_period).mean()

    for i in range(max(lookback, atr_period), len(df) - 1):
        row = df.iloc[i]
        current_atr = atr.iloc[i]

        candle_range = row.High - row.Low
        if candle_range == 0 or pd.isna(current_atr):
            continue

        body = abs(row.Close - row.Open)
        body_ratio = body / candle_range
        lower_wick = min(row.Open, row.Close) - row.Low
        upper_wick = row.High - max(row.Open, row.Close)
        recent_low = df.iloc[i - lookback : i].Low.min()
        recent_high = df.iloc[i - lookback : i].High.max()

        if trade_side in {"both", "buy"}:
            is_spike_low = (
                body_ratio <= max_body_ratio
                and lower_wick >= current_atr * atr_multiplier
                and lower_wick > upper_wick * 2
                and row.Low <= recent_low
            )
            if is_spike_low:
                next_row = df.iloc[i + 1]
                entry_price = float(next_row.Open)
                sl_price = float(row.Low - (current_atr * atr_buffer))
                risk = entry_price - sl_price
                if risk <= 0:
                    continue
                tp_price = float(entry_price + (risk * risk_reward))
                signals.append(
                    StrategySignal(
                        index=i + 1,
                        time=next_row.Datetime,
                        direction="BUY",
                        entry=entry_price,
                        reason="spike_low_atr_reversal",
                        sl=sl_price,
                        tp=tp_price,
                    )
                )

        if trade_side in {"both", "sell"}:
            is_spike_high = (
                body_ratio <= max_body_ratio
                and upper_wick >= current_atr * atr_multiplier
                and upper_wick > lower_wick * 2
                and row.High >= recent_high
            )
            if is_spike_high:
                next_row = df.iloc[i + 1]
                entry_price = float(next_row.Open)
                sl_price = float(row.High + (current_atr * atr_buffer))
                risk = sl_price - entry_price
                if risk <= 0:
                    continue
                tp_price = float(entry_price - (risk * risk_reward))
                signals.append(
                    StrategySignal(
                        index=i + 1,
                        time=next_row.Datetime,
                        direction="SELL",
                        entry=entry_price,
                        reason="spike_high_atr_reversal",
                        sl=sl_price,
                        tp=tp_price,
                    )
                )

    return signals
