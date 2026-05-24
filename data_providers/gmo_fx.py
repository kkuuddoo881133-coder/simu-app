from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


BASE_URL = "https://forex-api.coin.z.com/public/v1/klines"
INTRADAY_MIN_DATE = date(2023, 10, 28)
INTRADAY_INTERVALS = {"1min", "5min", "10min", "15min", "30min", "1hour"}
LONG_INTERVALS = {"4hour", "8hour", "12hour", "1day", "1week", "1month"}


@dataclass(frozen=True)
class GmoFxRequest:
    symbol: str
    price_type: str
    interval: str
    start_date: date
    end_date: date


class GmoFxError(RuntimeError):
    pass


def validate_request(req: GmoFxRequest) -> None:
    if req.end_date < req.start_date:
        raise GmoFxError("終了日は開始日以降にしてください。")
    if req.interval in INTRADAY_INTERVALS and req.start_date < INTRADAY_MIN_DATE:
        raise GmoFxError("GMO FX APIの分足/時間足は2023-10-28以降を指定してください。")
    if req.interval not in INTRADAY_INTERVALS | LONG_INTERVALS:
        raise GmoFxError(f"未対応の時間足です: {req.interval}")
    if req.price_type not in {"BID", "ASK"}:
        raise GmoFxError("price_type は BID または ASK を指定してください。")


def load_klines(req: GmoFxRequest, cache_dir: Path | str = ".cache/gmo_fx") -> pd.DataFrame:
    validate_request(req)
    cache_root = Path(cache_dir)
    frames = []
    for target_date in _iter_fetch_dates(req):
        frame = _load_one(req, target_date, cache_root)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return _empty_frame()

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["Datetime"]).sort_values("Datetime")
    start = pd.Timestamp(req.start_date)
    end = pd.Timestamp(req.end_date) + pd.Timedelta(days=1)
    return df[(df["Datetime"] >= start) & (df["Datetime"] < end)].reset_index(drop=True)


def _iter_fetch_dates(req: GmoFxRequest) -> Iterable[date]:
    if req.interval in LONG_INTERVALS:
        years = range(req.start_date.year, req.end_date.year + 1)
        for year in years:
            yield date(year, 1, 1)
        return

    current = req.start_date
    while current <= req.end_date:
        yield current
        current += timedelta(days=1)


def _load_one(req: GmoFxRequest, target_date: date, cache_root: Path) -> pd.DataFrame:
    date_token = str(target_date.year) if req.interval in LONG_INTERVALS else target_date.strftime("%Y%m%d")
    cache_file = (
        cache_root
        / req.symbol
        / req.price_type
        / req.interval
        / f"{date_token}.csv"
    )
    if cache_file.exists():
        return pd.read_csv(cache_file, parse_dates=["Datetime"])

    params = {
        "symbol": req.symbol,
        "priceType": req.price_type,
        "interval": req.interval,
        "date": date_token,
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 0:
        raise GmoFxError(f"GMO API error: {payload}")

    df = _normalize(payload.get("data", []), req)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file, index=False)
    return df


def _normalize(rows: list[dict], req: GmoFxRequest) -> pd.DataFrame:
    if not rows:
        return _empty_frame()

    df = pd.DataFrame(rows)
    df["Datetime"] = pd.to_datetime(df["openTime"].astype("int64"), unit="ms")
    df["Open"] = pd.to_numeric(df["open"])
    df["High"] = pd.to_numeric(df["high"])
    df["Low"] = pd.to_numeric(df["low"])
    df["Close"] = pd.to_numeric(df["close"])
    df["Symbol"] = req.symbol
    df["PriceType"] = req.price_type
    df["Interval"] = req.interval
    return df[["Datetime", "Open", "High", "Low", "Close", "Symbol", "PriceType", "Interval"]]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Datetime", "Open", "High", "Low", "Close", "Symbol", "PriceType", "Interval"]
    )

