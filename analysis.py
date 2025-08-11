# analysis.py
import os
import math
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from firebase_utils import get_secret

# Constants & tuning
YEARS_HISTORY = 8
HORIZONS_MONTHS = [6, 12, 18, 24, 48]
MIN_AVG_VOLUME = 30000
VOL_PENALTY = 0.5
LOGVOL_WEIGHT = 0.005

# Dhan endpoint placeholder - adjust if your Dhan docs differ
DHAN_CANDLES_URL = "https://api.dhan.co/v1/marketdata/candles"

def safe_get_json(url, headers=None, params=None, retries=2, timeout=20):
    import requests
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(1)
    return None

def fetch_dhan_candles(symbol, start_date, end_date, token):
    """
    Tries to fetch Dhan candles. Adjust mapping according to Dhan response shape if needed.
    symbol: string (e.g., RELIANCE or instrument token; adapt to your Dhan usage)
    """
    headers = {"Authorization": f"Bearer {token}"}
    params = {"symbol": symbol, "start": start_date.strftime("%Y-%m-%d"), "end": end_date.strftime("%Y-%m-%d"), "interval": "1d"}
    j = safe_get_json(DHAN_CANDLES_URL, headers=headers, params=params)
    if not j:
        return None
    # Normalize common shapes:
    if isinstance(j, dict) and "candles" in j:
        arr = j["candles"]
    elif isinstance(j, list):
        arr = j
    elif isinstance(j, dict) and "data" in j:
        arr = j["data"]
    else:
        # unknown shape
        arr = []
    if len(arr) == 0:
        return None
    df = pd.DataFrame(arr)
    # Map columns to open/high/low/close/volume/date if possible
    col_map = {}
    for c in df.columns:
        lc = c.lower()
        if "open" in lc: col_map[c] = "open"
        if "high" in lc: col_map[c] = "high"
        if "low" in lc: col_map[c] = "low"
        if "close" in lc or "last" in lc or "closeprice" in lc: col_map[c] = "close"
        if "volume" in lc: col_map[c] = "volume"
        if "date" in lc or "time" in lc or "timestamp" in lc:
            col_map[c] = "date"
    df = df.rename(columns=col_map)
    if "date" not in df.columns and df.shape[1] >= 1:
        # assume first column is timestamp/date
        df = df.reset_index().rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # ensure necessary columns exist
    for c in ["open", "high", "low", "close", "volume"]:
        if c not in df.columns:
            df[c] = np.nan
    return df[["open","high","low","close","volume"]]

def fetch_yfinance(symbol, years=YEARS_HISTORY):
    import yfinance as yf
    ticker = symbol if "." in symbol else f"{symbol}.NS"
    df = yf.Ticker(ticker).history(period=f"{years}y", interval="1d", actions=False)
    if df is None or df.empty:
        return None
    df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    df.index = pd.to_datetime(df.index)
    return df[["open","high","low","close","volume"]]

def get_history(symbol, dhan_token=None):
    end = datetime.now()
    start = end - timedelta(days=YEARS_HISTORY*365)
    if dhan_token:
        try:
            df = fetch_dhan_candles(symbol, start, end, dhan_token)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    # fallback
    return fetch_yfinance(symbol, YEARS_HISTORY)

def compute_indicators(df):
    df = df.copy()
    df["ret_1d"] = df["close"].pct_change()
    df["tr"] = (df["high"] - df["low"]).abs()
    df["atr"] = df["tr"].rolling(14, min_periods=1).mean()
    df["volatility_annual"] = df["ret_1d"].rolling(21, min_periods=1).std() * math.sqrt(252)
    return df

def score_for_horizon(df, months):
    if df is None or df.empty:
        return None
    end = df.index.max()
    lookback_days = int(months * 30)
    cutoff = end - pd.Timedelta(days=lookback_days)
    recent = df[df.index >= cutoff]
    if recent.empty or len(recent) < 10:
        return None
    total_return = (recent["close"].iloc[-1] / recent["close"].iloc[0]) - 1
    vol = recent["ret_1d"].std() * math.sqrt(252) if recent["ret_1d"].std() is not None else 0.0
    avg_vol = recent["volume"].mean() if "volume" in recent.columns else 0.0
    if pd.isna(avg_vol) or avg_vol < MIN_AVG_VOLUME:
        return None
    score = (total_return * 1.0) - (vol * VOL_PENALTY) + (math.log1p(avg_vol) * LOGVOL_WEIGHT)
    return {"return": float(total_return), "volatility": float(vol), "avg_vol": float(avg_vol), "score": float(score)}

def analyze_universe(symbols, use_dhan=True, use_news=False, news_key=None, min_avg_vol=MIN_AVG_VOLUME):
    """
    Returns: tops dict {horizon_months: DataFrame(top10)} and summary counts
    """
    # fetch Dhan token from Firebase if required
    dhan_token = None
    if use_dhan:
        dhan_token = get_secret("DHAN_TOKEN")  # uses firebase_utils

    results = {h: [] for h in HORIZONS_MONTHS}

    for sym in symbols:
        try:
            df = get_history(sym, dhan_token)
            if df is None:
                continue
            df = compute_indicators(df)
            for h in HORIZONS_MONTHS:
                sc = score_for_horizon(df, h)
                if sc:
                    sc.update({"symbol": sym, "horizon": h})
                    results[h].append(sc)
        except Exception:
            # ignore symbol errors for now
            continue

    # helper to compute target price (3x last close)
    def compute_target(sym):
        sub = get_history(sym, dhan_token)
        if sub is None or sub.empty:
            return None
        sub = compute_indicators(sub)
        last = sub.iloc[-1]
        if pd.isna(last["close"]):
            return None
        return float(last["close"] * 3)

    # helper to compute stop loss (last close - 1.5*ATR)
    def compute_stop(sym):
        sub = get_history(sym, dhan_token)
        if sub is None or sub.empty:
            return None
        sub = compute_indicators(sub)
        last = sub.iloc[-1]
        if pd.isna(last["atr"]):
            return None
        return float(last["close"] - 1.5 * last["atr"])

    # prepare top-10 per horizon and convert score->prob
    top_lists = {}
    for h in HORIZONS_MONTHS:
        rows = results[h]
        if not rows:
            top_lists[h] = pd.DataFrame()
            continue
        dfh = pd.DataFrame(rows)
        mn, mx = dfh["score"].min(), dfh["score"].max()
        if abs(mx - mn) < 1e-9:
            dfh["prob_est"] = 0.5
        else:
            dfh["prob_est"] = (dfh["score"] - mn) / (mx - mn)
        dfh = dfh.sort_values("prob_est", ascending=False).head(10).reset_index(drop=True)

        dfh["stop_loss_est"] = dfh["symbol"].apply(compute_stop)
        dfh["target_price_est"] = dfh["symbol"].apply(compute_target)
        dfh["reason"] = dfh.apply(
            lambda r: f"ret={r['return']:.2%}, vol={r['volatility']:.2f}, avgVol={int(r['avg_vol'])}", axis=1
        )
        top_lists[h] = dfh[
            ["symbol", "prob_est", "return", "volatility", "avg_vol", "score", "stop_loss_est", "target_price_est", "reason"]
        ]

    # save excel
    timestamp = int(time.time())
    out_file = f"top_stocks_{timestamp}.xlsx"
    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        for h, df_out in top_lists.items():
            if df_out.empty:
                pd.DataFrame([], columns=["symbol"]).to_excel(writer, sheet_name=f"{h}m", index=False)
            else:
                df_out.to_excel(writer, sheet_name=f"{h}m", index=False)

    return out_file, {h: len(results[h]) for h in HORIZONS_MONTHS}
