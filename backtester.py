from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategies.base import StrategySignal


@dataclass(frozen=True)
class BacktestConfig:
    take_profit_pips: float
    stop_loss_pips: float
    max_hold_bars: int
    allow_overlapping_entries: bool = True


def run_backtest(
    df: pd.DataFrame,
    signals: list[StrategySignal],
    config: BacktestConfig,
    execution_df: pd.DataFrame | None = None,
    bar_minutes: int = 1,
) -> pd.DataFrame:
    trades = []
    pip = 0.01
    has_bid_ask = {"BidOpen", "BidHigh", "BidLow", "BidClose", "AskOpen", "AskHigh", "AskLow", "AskClose"}.issubset(
        df.columns
    )
    execution = execution_df if execution_df is not None else df
    execution = execution.sort_values("Datetime").reset_index(drop=True)
    execution_has_bid_ask = {
        "BidOpen",
        "BidHigh",
        "BidLow",
        "BidClose",
        "AskOpen",
        "AskHigh",
        "AskLow",
        "AskClose",
    }.issubset(execution.columns)
    blocked_until: pd.Timestamp | None = None

    for signal in signals:
        if signal.index >= len(df) - 1:
            continue
        if not config.allow_overlapping_entries and blocked_until is not None and signal.time <= blocked_until:
            continue

        entry_row = df.iloc[signal.index]
        entry_time = pd.Timestamp(signal.time)
        entry_exec_idx = _nearest_datetime_index(execution, entry_time)
        entry_exec_row = execution.iloc[entry_exec_idx]
        entry = _entry_price(entry_exec_row, entry_row, signal, execution_has_bid_ask or has_bid_ask)
        if signal.tp is not None and signal.sl is not None:
            take_profit = float(signal.tp)
            stop_loss = float(signal.sl)
        elif signal.direction == "BUY":
            take_profit = entry + config.take_profit_pips * pip
            stop_loss = entry - config.stop_loss_pips * pip
        else:
            take_profit = entry - config.take_profit_pips * pip
            stop_loss = entry + config.stop_loss_pips * pip

        end_time = entry_time + pd.Timedelta(minutes=max(1, bar_minutes) * config.max_hold_bars - 1)
        exit_exec_idx = _last_datetime_index_at_or_before(execution, end_time)
        if exit_exec_idx < entry_exec_idx:
            exit_exec_idx = entry_exec_idx
        exit_price = _time_exit_price(execution.iloc[exit_exec_idx], signal, execution_has_bid_ask)
        exit_reason = "time_exit"

        for j in range(entry_exec_idx, exit_exec_idx + 1):
            row = execution.iloc[j]
            if signal.direction == "BUY":
                high = row.BidHigh if execution_has_bid_ask else row.High
                low = row.BidLow if execution_has_bid_ask else row.Low
                hit_tp = high >= take_profit
                hit_sl = low <= stop_loss
            else:
                high = row.AskHigh if execution_has_bid_ask else row.High
                low = row.AskLow if execution_has_bid_ask else row.Low
                hit_tp = low <= take_profit
                hit_sl = high >= stop_loss

            if hit_tp and hit_sl:
                exit_exec_idx = j
                exit_price = stop_loss
                exit_reason = "tp_sl_same_1m_bar_sl_first"
                break
            if hit_tp:
                exit_exec_idx = j
                exit_price = take_profit
                exit_reason = "take_profit"
                break
            if hit_sl:
                exit_exec_idx = j
                exit_price = stop_loss
                exit_reason = "stop_loss"
                break

        pnl_pips = (exit_price - entry) / pip if signal.direction == "BUY" else (entry - exit_price) / pip
        exit_time = pd.Timestamp(execution.iloc[exit_exec_idx].Datetime)
        trades.append(
            {
                "trade_no": len(trades) + 1,
                "signal_time": signal.time,
                "entry_time": signal.time,
                "exit_time": exit_time,
                "direction": signal.direction,
                "entry": round(entry, 3),
                "take_profit": round(take_profit, 3),
                "stop_loss": round(stop_loss, 3),
                "exit": round(exit_price, 3),
                "pips": round(pnl_pips, 1),
                "exit_reason": exit_reason,
                "signal_reason": signal.reason,
            }
        )
        if not config.allow_overlapping_entries:
            blocked_until = exit_time

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["equity"] = trades_df["pips"].cumsum()
    return trades_df


def _entry_price(exec_row: pd.Series, signal_row: pd.Series, signal: StrategySignal, has_bid_ask: bool) -> float:
    if not has_bid_ask:
        return float(signal.entry)
    if signal.direction == "BUY":
        return float(exec_row.AskOpen if "AskOpen" in exec_row else signal_row.AskOpen)
    return float(exec_row.BidOpen if "BidOpen" in exec_row else signal_row.BidOpen)


def _time_exit_price(row: pd.Series, signal: StrategySignal, has_bid_ask: bool) -> float:
    if not has_bid_ask:
        return float(row.Close)
    if signal.direction == "BUY":
        return float(row.BidClose)
    return float(row.AskClose)


def _nearest_datetime_index(df: pd.DataFrame, target: pd.Timestamp) -> int:
    matches = df.index[df["Datetime"] == target].tolist()
    if matches:
        return int(matches[0])
    return int(df["Datetime"].sub(target).abs().idxmin())


def _last_datetime_index_at_or_before(df: pd.DataFrame, target: pd.Timestamp) -> int:
    candidates = df.index[df["Datetime"] <= target].tolist()
    if candidates:
        return int(candidates[-1])
    return 0


def metrics(trades_df: pd.DataFrame) -> dict[str, float | int]:
    if trades_df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pips": 0.0,
            "average_pips": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    wins = trades_df[trades_df["pips"] > 0]
    losses = trades_df[trades_df["pips"] < 0]
    gross_profit = wins["pips"].sum()
    gross_loss = abs(losses["pips"].sum())
    equity = trades_df["equity"]
    drawdown = equity.cummax() - equity

    return {
        "trades": int(len(trades_df)),
        "win_rate": float(round(len(wins) / len(trades_df) * 100, 1)),
        "total_pips": float(round(trades_df["pips"].sum(), 1)),
        "average_pips": float(round(trades_df["pips"].mean(), 2)),
        "profit_factor": float(round(gross_profit / gross_loss, 2)) if gross_loss else 0.0,
        "max_drawdown": float(round(drawdown.max(), 1)),
    }
