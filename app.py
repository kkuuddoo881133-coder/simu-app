from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtester import BacktestConfig, metrics, run_backtest
from condition_store import STORE_PATH, load_conditions, save_condition
from data_providers.gmo_fx import GmoFxError, GmoFxRequest, load_klines
from data_providers.local_csv import DEFAULT_CSV_PATH, load_bid_ask_csv, resample_bid_ask
from strategies import head_and_shoulders, spike_low
from time_filters import (
    HOUR_OPTIONS,
    MARKET_EVENT_OPTIONS,
    TIMEZONE_OPTIONS,
    add_display_time_columns,
    add_trade_display_time_columns,
    filter_signals_by_hour_slots,
    hour_label,
    to_jst,
)


st.set_page_config(page_title="FX Backtest Lab", layout="wide")

STRATEGIES = {
    spike_low.DISPLAY_NAME: spike_low,
    head_and_shoulders.DISPLAY_NAME: head_and_shoulders,
}


@st.cache_data(show_spinner=False)
def load_gmo_data(symbol: str, price_type: str, interval: str, start_date: date, end_date: date) -> pd.DataFrame:
    req = GmoFxRequest(
        symbol=symbol,
        price_type=price_type,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    return load_klines(req)


@st.cache_data(show_spinner=False)
def load_local_data(csv_path: str, interval: str, start_date: date, end_date: date) -> pd.DataFrame:
    one_min = load_bid_ask_csv(csv_path, start_date=start_date, end_date=end_date)
    return resample_bid_ask(one_min, interval)


@st.cache_data(show_spinner=False)
def load_local_one_min(csv_path: str, start_date: date, end_date: date) -> pd.DataFrame:
    return load_bid_ask_csv(csv_path, start_date=start_date, end_date=end_date)


def main() -> None:
    st.title("FX Backtest Lab")

    with st.sidebar:
        st.header("Data")
        data_source = st.selectbox("データソース", ["ローカルCSV", "GMO API"])
        symbol = st.selectbox("通貨ペア", ["USD_JPY"])
        interval = st.selectbox("ローソク足", ["1min", "5min", "10min", "15min", "30min", "1hour", "4hour", "24hour"])
        default_end = date.today() - timedelta(days=1)
        default_start = max(date(2023, 10, 28), default_end - timedelta(days=7))
        start_date = st.date_input("開始日", default_start, min_value=date(2023, 10, 28))
        end_date = st.date_input("終了日", default_end, min_value=date(2023, 10, 28))
        if data_source == "ローカルCSV":
            csv_path = st.text_input("CSV", str(DEFAULT_CSV_PATH))
            price_type = "BID/ASK"
        else:
            csv_path = ""
            price_type = st.segmented_control("価格", ["BID", "ASK"], default="BID")

        st.header("Strategy")
        strategy_name = st.selectbox("手法", list(STRATEGIES.keys()))
        strategy = STRATEGIES[strategy_name]
        strategy_params = _strategy_controls(strategy_name)

        st.header("Time Filter")
        use_time_filter = st.toggle("時間帯でエントリーを絞る", value=False)
        time_filter_config = _time_filter_controls() if use_time_filter else None

        st.header("Exit")
        take_profit = st.number_input("TP pips", min_value=0.1, value=10.0, step=0.5)
        stop_loss = st.number_input("SL pips", min_value=0.1, value=8.0, step=0.5)
        max_hold_bars = st.number_input("最大保有本数", min_value=1, value=30, step=1)
        allow_overlapping_entries = st.toggle("重複エントリーを許可", value=True)

    try:
        with st.spinner("データを読み込んでいます..."):
            if data_source == "ローカルCSV":
                one_min_df = load_local_one_min(csv_path, start_date, end_date)
                df = resample_bid_ask(one_min_df, interval)
            else:
                one_min_df = None
                df = load_gmo_data(symbol, price_type, _gmo_interval(interval), start_date, end_date)
    except (GmoFxError, Exception) as exc:
        st.error(f"データ取得に失敗しました: {exc}")
        return

    if df.empty:
        st.warning("指定期間のデータがありません。ローカルCSVを更新してから再度試してください。")
        return

    df = add_display_time_columns(df)
    if one_min_df is not None:
        one_min_df = add_display_time_columns(one_min_df)

    signals = strategy.find_signals(df, **strategy_params)
    raw_signal_count = len(signals)
    if time_filter_config:
        signals = _apply_time_filter(signals, time_filter_config)
    trades_df = run_backtest(
        df,
        signals,
        BacktestConfig(
            take_profit_pips=take_profit,
            stop_loss_pips=stop_loss,
            max_hold_bars=int(max_hold_bars),
            allow_overlapping_entries=allow_overlapping_entries,
        ),
        execution_df=one_min_df,
        bar_minutes=_interval_minutes(interval),
    )
    trades_df = add_trade_display_time_columns(trades_df)
    summary = metrics(trades_df)

    _metric_row(summary, len(df), len(signals), df, raw_signal_count)
    _save_condition_panel(
        data_source=data_source,
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        csv_path=csv_path,
        price_type=price_type,
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        time_filter_config=time_filter_config,
        exit_config={
            "take_profit_pips": take_profit,
            "stop_loss_pips": stop_loss,
            "max_hold_bars": int(max_hold_bars),
            "allow_overlapping_entries": allow_overlapping_entries,
        },
        summary=summary,
        candles=len(df),
        raw_signals=raw_signal_count,
        filtered_signals=len(signals),
    )
    left, right = st.columns([1.4, 1])
    with left:
        st.plotly_chart(_price_chart(df, trades_df), width="stretch")
    with right:
        st.plotly_chart(_equity_chart(trades_df), width="stretch")

    st.subheader("Trades")
    st.dataframe(_trades_display_df(trades_df), width="stretch", hide_index=True)

    if not trades_df.empty:
        st.subheader("Trade Chart")
        chart_cols = st.columns([1, 1, 2, 1])
        max_trade_no = int(trades_df["trade_no"].max())
        with chart_cols[0]:
            trade_no = st.number_input("Trade No", min_value=1, max_value=max_trade_no, value=1, step=1)
        with chart_cols[1]:
            context_bars = st.number_input("前後の本数", min_value=5, max_value=300, value=60, step=5)
        selected_trade = int(trade_no)
        selected = trades_df.loc[trades_df["trade_no"] == selected_trade].iloc[0]
        chart_cols[2].metric("方向", selected["direction"])
        chart_cols[3].metric("Pips", selected["pips"])
        st.plotly_chart(_trade_chart(df, trades_df, selected_trade, int(context_bars)), width="stretch")

    with st.expander("取得データ"):
        st.dataframe(_market_data_display_df(df.tail(200)), width="stretch", hide_index=True)


def _strategy_controls(strategy_name: str) -> dict:
    if strategy_name == spike_low.DISPLAY_NAME:
        return {
            "trade_side": st.selectbox("売買方向", ["both", "buy", "sell"]),
            "atr_period": st.slider("ATR期間", 3, 100, 14, 1),
            "atr_multiplier": st.slider("ヒゲ ATR倍率", 0.1, 5.0, 1.0, 0.1),
            "max_body_ratio": st.slider("最大実体比率", 0.01, 0.8, 0.25, 0.01),
            "lookback": st.slider("直近高値/安値 判定本数", 3, 100, 20, 1),
            "atr_buffer": st.slider("SL ATRバッファ", 0.0, 2.0, 0.2, 0.05),
            "risk_reward": st.slider("リスクリワード", 0.1, 10.0, 2.0, 0.1),
        }

    return {
        "trade_side": st.selectbox("売買方向", ["both", "buy", "sell"]),
        "pivot_window": st.slider("山谷の検出幅", 2, 30, 5, 1),
        "shoulder_tolerance_pips": st.slider("肩の許容差 pips", 1.0, 50.0, 15.0, 0.5),
        "min_head_gap_pips": st.slider("頭の突出 pips", 1.0, 50.0, 10.0, 0.5),
    }


def _time_filter_controls() -> dict:
    mode = st.radio("選び方", ["JSTで1時間ずつ選ぶ", "市場イベントを選ぶ", "市場の現地時間で1時間ずつ選ぶ"])
    if mode == "JSTで1時間ずつ選ぶ":
        all_hours = st.checkbox("JST 全時間", value=False)
        selected_hours = HOUR_OPTIONS if all_hours else _hour_checkbox_grid("JST 対象時間", "jst", list(range(8, 15)))
        return {
            "mode": mode,
            "basis_label": "日本時間 JST",
            "timezone": TIMEZONE_OPTIONS["日本時間 JST"],
            "hours": selected_hours,
        }

    if mode == "市場イベントを選ぶ":
        event_name = st.selectbox("市場イベント", list(MARKET_EVENT_OPTIONS.keys()))
        timezone_name, selected_hours = MARKET_EVENT_OPTIONS[event_name]
        return {
            "mode": mode,
            "basis_label": event_name,
            "timezone": timezone_name,
            "hours": selected_hours,
        }

    basis_label = st.selectbox("市場", ["ロンドン現地時間 DST自動", "ニューヨーク現地時間 DST自動"])
    selected_hours = _hour_checkbox_grid("現地時間 対象時間", "market_local", [8, 9, 10])
    return {
        "mode": mode,
        "basis_label": basis_label,
        "timezone": TIMEZONE_OPTIONS[basis_label],
        "hours": selected_hours,
    }


def _apply_time_filter(signals: list, config: dict) -> list:
    return filter_signals_by_hour_slots(
        signals,
        config["timezone"],
        config["hours"],
    )


def _save_condition_panel(
    *,
    data_source: str,
    symbol: str,
    interval: str,
    start_date: date,
    end_date: date,
    csv_path: str,
    price_type: str,
    strategy_name: str,
    strategy_params: dict,
    time_filter_config: dict | None,
    exit_config: dict,
    summary: dict,
    candles: int,
    raw_signals: int,
    filtered_signals: int,
) -> None:
    with st.expander("条件保存", expanded=False):
        name = st.text_input("条件名", value=f"{strategy_name} {interval} {start_date} to {end_date}")
        note = st.text_area("メモ", value="", height=80)
        payload = {
            "name": name,
            "note": note,
            "data": {
                "source": data_source,
                "symbol": symbol,
                "interval": interval,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "csv_path": csv_path,
                "price_type": price_type,
            },
            "strategy": {
                "name": strategy_name,
                "params": strategy_params,
            },
            "time_filter": time_filter_config,
            "exit": exit_config,
            "result": {
                "candles": candles,
                "raw_signals": raw_signals,
                "filtered_signals": filtered_signals,
                **summary,
            },
        }
        st.code(str(STORE_PATH), language="text")
        if st.button("現在条件を保存"):
            path = save_condition(payload)
            st.success(f"保存しました: {path}")

        records = load_conditions()
        if records:
            st.caption("最近保存した条件")
            recent = [
                {
                    "saved_at_jst": item.get("saved_at_jst"),
                    "name": item.get("name"),
                    "strategy": item.get("strategy", {}).get("name"),
                    "interval": item.get("data", {}).get("interval"),
                    "total_pips": item.get("result", {}).get("total_pips"),
                    "trades": item.get("result", {}).get("trades"),
                    "win_rate": item.get("result", {}).get("win_rate"),
                }
                for item in records[-10:]
            ]
            st.dataframe(pd.DataFrame(recent), width="stretch", hide_index=True)


def _hour_checkbox_grid(label: str, key_prefix: str, default_hours: list[int]) -> list[int]:
    st.caption(label)
    selected_hours: list[int] = []
    columns = st.columns(4)
    defaults = set(default_hours)
    for hour in HOUR_OPTIONS:
        with columns[hour % 4]:
            checked = st.checkbox(hour_label(hour), value=hour in defaults, key=f"{key_prefix}_hour_{hour}")
        if checked:
            selected_hours.append(hour)
    return selected_hours


def _trades_display_df(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df
    result = trades_df.copy()
    jst_cols = {"signal_time_jst", "entry_time_jst", "exit_time_jst"} & set(result.columns)
    if jst_cols:
        result = result.drop(columns=[col for col in ["signal_time", "entry_time", "exit_time"] if col in result.columns])
        result = result.rename(
            columns={
                "signal_time_jst": "signal_time(JST)",
                "entry_time_jst": "entry_time(JST)",
                "exit_time_jst": "exit_time(JST)",
            }
        )
    preferred = [
        "trade_no",
        "signal_time(JST)",
        "entry_time(JST)",
        "exit_time(JST)",
        "direction",
        "entry",
        "take_profit",
        "stop_loss",
        "exit",
        "pips",
        "exit_reason",
        "signal_reason",
        "equity",
    ]
    return result[[col for col in preferred if col in result.columns]]


def _market_data_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if "DatetimeJST" in result.columns:
        result = result.drop(columns=["Datetime"], errors="ignore")
        result = result.rename(columns={"DatetimeJST": "Datetime(JST)"})
        ordered = ["Datetime(JST)"] + [col for col in result.columns if col != "Datetime(JST)"]
        result = result[ordered]
    return result


def _gmo_interval(interval: str) -> str:
    if interval == "24hour":
        return "1day"
    return interval


def _interval_minutes(interval: str) -> int:
    return {
        "1min": 1,
        "5min": 5,
        "10min": 10,
        "15min": 15,
        "30min": 30,
        "1hour": 60,
        "4hour": 240,
        "24hour": 1440,
    }[interval]


def _metric_row(summary: dict, candles: int, signals: int, df: pd.DataFrame, raw_signals: int) -> None:
    cols = st.columns(11)
    cols[0].metric("ローソク足", f"{candles:,}")
    cols[1].metric("シグナル", f"{signals:,}", delta=f"raw {raw_signals:,}" if raw_signals != signals else None)
    cols[2].metric("トレード", summary["trades"])
    cols[3].metric("勝率", f"{summary['win_rate']}%")
    cols[4].metric("合計Pips", summary["total_pips"])
    cols[5].metric("平均Pips", summary["average_pips"])
    cols[6].metric("PF", summary["profit_factor"])
    cols[7].metric("最大DD", summary["max_drawdown"])
    if "SpreadClosePips" in df.columns and not df.empty:
        cols[8].metric("最大終値Spread", f"{df['SpreadClosePips'].max():.2f}")
    if "MaxRangeSpreadPips" in df.columns and not df.empty:
        cols[9].metric("最大レンジSpread", f"{df['MaxRangeSpreadPips'].max():.2f}")


def _price_chart(df: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
    x_col = "DatetimeJST" if "DatetimeJST" in df.columns else "Datetime"
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df[x_col],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="USDJPY",
        )
    )
    if not trades_df.empty:
        buys = trades_df[trades_df["direction"] == "BUY"]
        sells = trades_df[trades_df["direction"] == "SELL"]
        entry_col = "entry_time_jst" if "entry_time_jst" in trades_df.columns else "entry_time"
        fig.add_trace(
            go.Scatter(
                x=buys[entry_col],
                y=buys["entry"],
                mode="markers",
                marker=dict(symbol="triangle-up", size=11, color="#16a34a"),
                name="BUY",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sells[entry_col],
                y=sells["entry"],
                mode="markers",
                marker=dict(symbol="triangle-down", size=11, color="#dc2626"),
                name="SELL",
            )
        )
    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        xaxis_title="JST",
    )
    return fig


def _trade_chart(df: pd.DataFrame, trades_df: pd.DataFrame, trade_no: int, context_bars: int) -> go.Figure:
    trade = trades_df.loc[trades_df["trade_no"] == trade_no].iloc[0]
    entry_time = pd.Timestamp(trade["entry_time"])
    exit_time = pd.Timestamp(trade["exit_time"])
    entry_time_jst = to_jst(entry_time).tz_localize(None)
    exit_time_jst = to_jst(exit_time).tz_localize(None)
    entry_matches = df.index[df["Datetime"] == entry_time].tolist()
    exit_matches = df.index[df["Datetime"] == exit_time].tolist()
    if not entry_matches:
        entry_idx = int(df["Datetime"].sub(entry_time).abs().idxmin())
    else:
        entry_idx = int(entry_matches[0])
    if not exit_matches:
        exit_idx = int(df["Datetime"].sub(exit_time).abs().idxmin())
    else:
        exit_idx = int(exit_matches[0])

    start_idx = max(0, min(entry_idx, exit_idx) - context_bars)
    end_idx = min(len(df) - 1, max(entry_idx, exit_idx) + context_bars)
    window = df.iloc[start_idx : end_idx + 1].copy()
    x_col = "DatetimeJST" if "DatetimeJST" in window.columns else "Datetime"

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=window[x_col],
            open=window["Open"],
            high=window["High"],
            low=window["Low"],
            close=window["Close"],
            name="Mid",
            increasing_line_color="#16a34a",
            decreasing_line_color="#dc2626",
        )
    )
    marker_symbol = "triangle-up" if trade["direction"] == "BUY" else "triangle-down"
    fig.add_trace(
        go.Scatter(
            x=[entry_time_jst if x_col == "DatetimeJST" else entry_time],
            y=[trade["entry"]],
            mode="markers",
            marker=dict(size=13, color="#2563eb", symbol=marker_symbol),
            name="Entry",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[exit_time_jst if x_col == "DatetimeJST" else exit_time],
            y=[trade["exit"]],
            mode="markers",
            marker=dict(size=13, color="#111827", symbol="x"),
            name="Exit",
        )
    )
    fig.add_hline(y=trade["take_profit"], line_dash="dot", line_color="#16a34a", annotation_text="TP")
    fig.add_hline(y=trade["stop_loss"], line_dash="dot", line_color="#dc2626", annotation_text="SL")
    fig.update_layout(
        title=f"Trade {trade_no} | {trade['direction']} | {trade['pips']} pips | {trade['exit_reason']}",
        height=560,
        margin=dict(l=10, r=10, t=45, b=10),
        xaxis_rangeslider_visible=False,
        xaxis_title="JST",
        yaxis_title="USDJPY",
    )
    return fig


def _equity_chart(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not trades_df.empty:
        x_col = "exit_time_jst" if "exit_time_jst" in trades_df.columns else "exit_time"
        fig.add_trace(
            go.Scatter(
                x=trades_df[x_col],
                y=trades_df["equity"],
                mode="lines+markers",
                name="Equity",
                line=dict(color="#2563eb", width=2),
            )
        )
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Pips", xaxis_title="JST")
    return fig


if __name__ == "__main__":
    main()
