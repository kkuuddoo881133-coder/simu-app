from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_CSV_PATH = Path("data/gmo_fx/USD_JPY/1min_bid_ask_spread.csv")

RESAMPLE_RULES = {
    "1min": None,
    "5min": "5min",
    "10min": "10min",
    "15min": "15min",
    "30min": "30min",
    "1hour": "1h",
    "4hour": "4h",
    "24hour": "24h",
}


def load_bid_ask_csv(
    path: Path | str = DEFAULT_CSV_PATH,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return _empty_bid_ask_frame()

    df = pd.read_csv(csv_path, parse_dates=["Datetime"])
    df = df.sort_values("Datetime").drop_duplicates(subset=["Datetime"])

    if start_date:
        df = df[df["Datetime"] >= pd.Timestamp(start_date)]
    if end_date:
        end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        df = df[df["Datetime"] < end]

    return df.reset_index(drop=True)


def resample_bid_ask(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    if df.empty:
        return df
    if interval not in RESAMPLE_RULES:
        raise ValueError(f"未対応の時間足です: {interval}")
    rule = RESAMPLE_RULES[interval]
    if rule is None:
        return with_mid_ohlc(df.copy())

    working = df.set_index("Datetime")
    agg = {
        "BidOpen": "first",
        "BidHigh": "max",
        "BidLow": "min",
        "BidClose": "last",
        "AskOpen": "first",
        "AskHigh": "max",
        "AskLow": "min",
        "AskClose": "last",
        "SpreadOpen": "first",
        "SpreadHigh": "max",
        "SpreadLow": "min",
        "SpreadClose": "last",
        "SpreadClosePips": "last",
        "MaxRangeSpread": "max",
        "MaxRangeSpreadPips": "max",
    }
    resampled = working.resample(rule, label="left", closed="left").agg(agg)
    resampled = resampled.dropna(subset=["BidOpen", "AskOpen"]).reset_index()
    return with_mid_ohlc(resampled)


def with_mid_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    df["Open"] = (df["BidOpen"] + df["AskOpen"]) / 2
    df["High"] = (df["BidHigh"] + df["AskHigh"]) / 2
    df["Low"] = (df["BidLow"] + df["AskLow"]) / 2
    df["Close"] = (df["BidClose"] + df["AskClose"]) / 2
    return df


def _empty_bid_ask_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Datetime",
            "BidOpen",
            "BidHigh",
            "BidLow",
            "BidClose",
            "AskOpen",
            "AskHigh",
            "AskLow",
            "AskClose",
            "SpreadOpen",
            "SpreadHigh",
            "SpreadLow",
            "SpreadClose",
            "SpreadClosePips",
            "MaxRangeSpread",
            "MaxRangeSpreadPips",
        ]
    )
