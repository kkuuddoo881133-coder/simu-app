# FX Backtest Lab

USD/JPY strategy backtesting app built with Streamlit.

The app is designed around one local 1-minute BID/ASK CSV downloaded from GMO Coin Forex public API. Higher timeframes are generated from that 1-minute file inside the app.

## Folder

```bash
cd /Users/yoheikudo/simu-app/fx-backtest-lab
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `(.venv)` is already shown in Terminal, the virtual environment is already active.

## Run The Web App

```bash
streamlit run app.py --server.port 8502
```

Open:

```text
http://localhost:8502
```

If port 8502 is already in use:

```bash
lsof -tiTCP:8502 -sTCP:LISTEN | xargs kill
streamlit run app.py --server.port 8502
```

## Update Local CSV

The local CSV is the main data source.

```text
data/gmo_fx/USD_JPY/1min_bid_ask_spread.csv
```

Update from the day after the latest CSV row through yesterday:

```bash
python scripts/update_gmo_csv.py
```

Update a specific range:

```bash
python scripts/update_gmo_csv.py --start 2026-05-18 --end 2026-05-22
```

To intentionally include today:

```bash
python scripts/update_gmo_csv.py --end YYYY-MM-DD
```

GMO Forex public KLine data does not require an API key.

## Data Design

The CSV stores 1-minute BID/ASK OHLC:

```text
Datetime
BidOpen, BidHigh, BidLow, BidClose
AskOpen, AskHigh, AskLow, AskClose
SpreadOpen, SpreadHigh, SpreadLow, SpreadClose
SpreadClosePips
MaxRangeSpread, MaxRangeSpreadPips
```

Spread columns:

```text
SpreadClose = AskClose - BidClose
SpreadClosePips = SpreadClose / 0.01
MaxRangeSpread = AskHigh - BidLow
```

`MaxRangeSpread` is not a true simultaneous spread. It is a rough stress/range indicator for that 1-minute candle.

## Time Handling

GMO timestamps are treated as UTC internally.

The web UI displays times in JST:

- charts use JST
- trade table uses JST columns
- market data preview uses JST

Time filters support:

- JST hour slots from `00:00-01:00` through `23:00-00:00`
- market event presets such as London fix
- London/New York local hour slots with DST handled automatically

For London/New York filters, the app converts each signal timestamp into the market's local timezone using Python timezone rules. This avoids manual JST conversion mistakes across daylight saving time.

## Backtest Rules

When BID/ASK data is available:

- BUY entry uses `AskOpen`
- BUY exit uses `Bid`
- SELL entry uses `BidOpen`
- SELL exit uses `Ask`

This means spread cost is naturally included in the result.

If the strategy signal is generated on a higher timeframe, exits are still checked on the 1-minute CSV when using the local CSV source.

If TP and SL both hit inside the same 1-minute candle, the app assumes SL first:

```text
tp_sl_same_1m_bar_sl_first
```

## Strategies

Strategy files live under:

```text
strategies/
```

Current strategies:

- `spike_low.py`: `Spike`, ATR-based spike low/high reversal
- `head_and_shoulders.py`: head and shoulders / inverse head and shoulders prototype

The web UI reads each strategy's `DISPLAY_NAME` and calls its `find_signals(...)` function.

## Spike Parameters

Current `Spike` parameters:

- `trade_side`: both / buy / sell
- `atr_period`: ATR lookback period
- `atr_multiplier`: required wick length as a multiple of ATR
- `max_body_ratio`: maximum candle body ratio versus full candle range
- `lookback`: recent high/low lookback window
- `atr_buffer`: SL buffer beyond the spike wick, expressed as ATR multiple
- `risk_reward`: TP distance as a multiple of risk

`Spike` calculates its own TP/SL from the spike wick and ATR. When a strategy signal provides TP/SL, the backtester uses those strategy-level prices instead of the global fixed TP/SL pips.

## Common Commands

Start from the project folder:

```bash
cd /Users/yoheikudo/simu-app/fx-backtest-lab
source .venv/bin/activate
```

Run app:

```bash
streamlit run app.py --server.port 8502
```

Update CSV:

```bash
python scripts/update_gmo_csv.py
```

Check syntax:

```bash
python -m py_compile app.py backtester.py strategies/spike_low.py
```

## Saved Conditions

When you find a useful setup in the web UI, open `条件保存`, add a name or note, and click `現在条件を保存`.

Saved conditions are appended to:

```text
saved_conditions/conditions.jsonl
```

Each line is one saved condition with:

- data range and timeframe
- strategy parameters
- time filter
- exit settings
- result summary
- memo

## Notes

- GMO intraday FX KLine data starts from 2023-10-28.
- The app is for research/backtesting only.
- It does not place live trades.
- Large CSV files should stay local and should not be committed to Git.
