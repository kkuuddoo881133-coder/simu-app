from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

from strategies.base import StrategySignal


UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")

TIMEZONE_OPTIONS = {
    "日本時間 JST": "Asia/Tokyo",
    "ニューヨーク現地時間 DST自動": "America/New_York",
    "ロンドン現地時間 DST自動": "Europe/London",
}

MARKET_EVENT_OPTIONS = {
    "ロンドンフィックス 16時台 London local DST自動": ("Europe/London", [16]),
    "ロンドンオープン 08時台 London local DST自動": ("Europe/London", [8]),
    "ロンドンクローズ 16時台 London local DST自動": ("Europe/London", [16]),
    "NYオープン 09時台 New York local DST自動": ("America/New_York", [9]),
    "NY午前 09-11時台 New York local DST自動": ("America/New_York", [9, 10, 11]),
    "NYクローズ 16時台 New York local DST自動": ("America/New_York", [16]),
}

HOUR_OPTIONS = list(range(24))


def hour_label(hour: int) -> str:
    return f"{hour:02d}:00-{(hour + 1) % 24:02d}:00"


def filter_signals_by_hour_slots(
    signals: list[StrategySignal],
    timezone_name: str,
    selected_hours: list[int],
) -> list[StrategySignal]:
    if not selected_hours:
        return []
    selected = set(selected_hours)
    zone = ZoneInfo(timezone_name)
    return [signal for signal in signals if to_timezone(signal.time, zone).hour in selected]


def add_display_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Datetime" not in df.columns:
        return df
    result = df.copy()
    result["DatetimeJST"] = result["Datetime"].apply(to_jst).dt.tz_localize(None)
    return result


def add_trade_display_time_columns(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df
    result = trades_df.copy()
    for col in ["signal_time", "entry_time", "exit_time"]:
        if col in result.columns:
            result[f"{col}_jst"] = result[col].apply(to_jst).dt.tz_localize(None)
    return result


def to_jst(value) -> pd.Timestamp:
    return to_timezone(value, JST)


def to_timezone(value, zone: ZoneInfo) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(UTC)
    else:
        ts = ts.tz_convert(UTC)
    return ts.tz_convert(zone)
