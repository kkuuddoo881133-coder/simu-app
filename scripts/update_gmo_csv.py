from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_providers.gmo_fx import GmoFxRequest, load_klines


DEFAULT_START = date(2023, 10, 28)
DEFAULT_OUTPUT = Path("data/gmo_fx/USD_JPY/1min_bid_ask_spread.csv")
PIP = 0.01


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    start_date = parse_date(args.start) if args.start else infer_start_date(output_path)
    end_date = parse_date(args.end) if args.end else date.today() - timedelta(days=1)

    if end_date < start_date:
        print(f"No update needed. start={start_date} end={end_date}")
        return

    print(f"Fetching {args.symbol} {args.interval} BID/ASK from {start_date} to {end_date}")
    bid = load_klines(GmoFxRequest(args.symbol, "BID", args.interval, start_date, end_date))
    ask = load_klines(GmoFxRequest(args.symbol, "ASK", args.interval, start_date, end_date))
    merged = merge_bid_ask(bid, ask)

    if merged.empty:
        print("No rows returned. FX market may have been closed for the selected range.")
        return

    if output_path.exists():
        existing = pd.read_csv(output_path, parse_dates=["Datetime"])
        merged = pd.concat([existing, merged], ignore_index=True)

    merged = merged.sort_values("Datetime").drop_duplicates(subset=["Datetime"], keep="last")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)

    print(f"Wrote {len(merged):,} rows -> {output_path}")
    print(f"Range: {merged['Datetime'].min()} to {merged['Datetime'].max()}")
    print(f"Max SpreadClosePips: {merged['SpreadClosePips'].max():.2f}")
    print(f"Max Range Spread Pips: {merged['MaxRangeSpreadPips'].max():.2f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update local GMO FX BID/ASK 1-minute CSV.")
    parser.add_argument("--symbol", default="USD_JPY")
    parser.add_argument("--interval", default="1min", choices=["1min"])
    parser.add_argument("--start", help="YYYY-MM-DD. Defaults to the day after the latest CSV row.")
    parser.add_argument("--end", help="YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def infer_start_date(output_path: Path) -> date:
    if not output_path.exists():
        return DEFAULT_START
    existing = pd.read_csv(output_path, usecols=["Datetime"], parse_dates=["Datetime"])
    if existing.empty:
        return DEFAULT_START
    return existing["Datetime"].max().date() + timedelta(days=1)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def merge_bid_ask(bid: pd.DataFrame, ask: pd.DataFrame) -> pd.DataFrame:
    bid_cols = bid.rename(
        columns={
            "Open": "BidOpen",
            "High": "BidHigh",
            "Low": "BidLow",
            "Close": "BidClose",
        }
    )[["Datetime", "BidOpen", "BidHigh", "BidLow", "BidClose"]]
    ask_cols = ask.rename(
        columns={
            "Open": "AskOpen",
            "High": "AskHigh",
            "Low": "AskLow",
            "Close": "AskClose",
        }
    )[["Datetime", "AskOpen", "AskHigh", "AskLow", "AskClose"]]
    df = bid_cols.merge(ask_cols, on="Datetime", how="inner")
    if df.empty:
        return df

    df["SpreadOpen"] = df["AskOpen"] - df["BidOpen"]
    df["SpreadHigh"] = df["AskHigh"] - df["BidHigh"]
    df["SpreadLow"] = df["AskLow"] - df["BidLow"]
    df["SpreadClose"] = df["AskClose"] - df["BidClose"]
    df["SpreadClosePips"] = df["SpreadClose"] / PIP
    df["MaxRangeSpread"] = df["AskHigh"] - df["BidLow"]
    df["MaxRangeSpreadPips"] = df["MaxRangeSpread"] / PIP

    numeric_cols = [col for col in df.columns if col != "Datetime"]
    df[numeric_cols] = df[numeric_cols].round(6)
    return df


if __name__ == "__main__":
    main()

