"""Build per-symbol chart JSONs for the dashboard's deep-dive pages.

Runs in the GitHub Action after fetch_data.py / compute_signals.py. For each
universe ticker, writes <out>/<TICKER>.json with five timeframes:

  m5  : 5-minute bars, ~1 week   (fetched here; yfinance cap ~60d)
  h1  : hourly bars,  ~1 month   (fetched here; cap ~730d)
  d1  : daily bars,   12 months  (from data/prices.csv — same series the
  w1  : weekly bars,  10 years    stage engine uses, resampled)
  mo1 : monthly bars, 25 years   (fetched here, period=max capped 25y)

Each timeframe carries precomputed indicators (portal-standard parameters):
Bollinger(20, 2σ), MACD(12/26/9), RSI(14, Wilder), MFI(14). Daily and weekly
also carry confirmed swing pivots (HH/LH/HL/LL, causal ±5 lookback).
Bars are [unix_sec, open, high, low, close, volume]; indicator arrays align
1:1 with bars (nulls where undefined).

Usage: python chart_data.py --out _site/charts
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from compute_signals import UNIVERSE, find_pivots, causal_trend_history

HERE = Path.cwd()  # runs from public repo root; this file lives in the private repo
LOOKBACK = 5


# ---- indicators (portal-standard) -----------------------------------------

def bollinger(close, window=20, n_std=2.0):
    mid = close.rolling(window).mean()
    sd = close.rolling(window).std()
    return mid, mid + n_std * sd, mid - n_std * sd


def macd(close, fast=12, slow=26, signal=9):
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def ewo(high, low, fast=5, slow=35):
    """Elliott Wave Oscillator: SMA(median,5) - SMA(median,35), median=(H+L)/2."""
    median = (high + low) / 2.0
    return median.rolling(fast).mean() - median.rolling(slow).mean()


def mfi(high, low, close, volume, window=14):
    typical = (high + low + close) / 3.0
    raw = typical * volume
    delta = typical.diff()
    pos = raw.where(delta > 0, 0.0).rolling(window).sum()
    neg = raw.where(delta < 0, 0.0).rolling(window).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        mr = pos / neg
    return 100 - (100 / (1 + mr))


def _clean(series):
    return [None if (v is None or (isinstance(v, float) and not math.isfinite(v)))
            else round(float(v), 4) for v in series]


def frame_to_tab(df, with_pivots=False):
    """df: OHLCV DataFrame (capitalized or lowercase cols) -> tab dict."""
    df = df.rename(columns={c: c.lower() for c in df.columns}).dropna(
        subset=["open", "high", "low", "close"])
    if df.empty or len(df) < 5:
        return None
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    v = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)
    ts = [int(pd.Timestamp(t).timestamp()) for t in df.index]
    bars = [[ts[i], round(float(o.iloc[i]), 4), round(float(h.iloc[i]), 4),
             round(float(l.iloc[i]), 4), round(float(c.iloc[i]), 4),
             int(v.iloc[i]) if math.isfinite(v.iloc[i]) else 0]
            for i in range(len(df))]
    mid, up, lo = bollinger(c)
    m_line, m_sig, m_hist = macd(c)
    tab = {
        "bars": bars,
        "bb": {"mid": _clean(mid), "up": _clean(up), "lo": _clean(lo)},
        "macd": {"line": _clean(m_line), "sig": _clean(m_sig), "hist": _clean(m_hist)},
        "rsi": _clean(rsi(c)),
        "mfi": _clean(mfi(h, l, c, v)),
        "ewo": _clean(ewo(h, l)),
    }
    if with_pivots and len(df) > 2 * LOOKBACK + 5:
        piv = find_pivots(h, l, LOOKBACK)
        marks = []
        last_h = last_l = None
        for i in range(len(df)):
            if piv.iloc[i]["high_pivot"]:
                val = float(h.iloc[i])
                lab = ("HH" if val > last_h else "LH") if last_h is not None else "H"
                last_h = val
                marks.append({"t": ts[i], "p": round(val, 4), "label": lab, "kind": "high"})
            if piv.iloc[i]["low_pivot"]:
                val = float(l.iloc[i])
                lab = ("HL" if val > last_l else "LL") if last_l is not None else "L"
                last_l = val
                marks.append({"t": ts[i], "p": round(val, 4), "label": lab, "kind": "low"})
        tab["pivots"] = marks
        states = causal_trend_history(h, l, LOOKBACK)
        tab["state"] = str(states.iloc[-1])
    return tab


def batch_download(tickers, period, interval):
    try:
        df = yf.download(tickers, period=period, interval=interval,
                         auto_adjust=True, progress=False, group_by="ticker",
                         threads=True)
    except Exception as e:
        print(f"WARN batch {interval}/{period} failed: {e}", file=sys.stderr)
        return {}
    out = {}
    if df is None or df.empty:
        return out
    for t in tickers:
        try:
            sub = df[t].dropna(how="all")
            if len(sub) >= 5:
                out[t] = sub
        except KeyError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site/charts")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = list(UNIVERSE)

    # intraday + monthly fetched fresh; daily/weekly from the relay CSV
    m5 = batch_download(tickers, "5d", "5m")   # 5 trading days = 1 week
    h1 = batch_download(tickers, "1mo", "1h")
    mo = batch_download(tickers, "max", "1mo")  # trimmed to 25y below

    px = pd.read_csv(HERE / "data" / "prices.csv", parse_dates=["date"])
    try:
        fu = pd.read_csv(HERE / "data" / "fundamentals.csv").set_index("ticker")
    except Exception:
        fu = pd.DataFrame()
    signals = {}
    sig_path = HERE / "docs" / "signals.json"
    if sig_path.exists():
        signals = {r["ticker"]: r for r in
                   json.loads(sig_path.read_text()).get("rows", [])}

    n_ok = 0
    for t in tickers:
        g = px[px.ticker == t]
        daily = g.set_index("date")[["open", "high", "low", "close", "volume"]].sort_index()
        if daily.empty:
            continue
        weekly = daily.resample("W-FRI").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna()
        tabs = {
            "m5": frame_to_tab(m5.get(t)) if t in m5 else None,
            "h1": frame_to_tab(h1.get(t), with_pivots=True) if t in h1 else None,
            "d1": frame_to_tab(daily.tail(260), with_pivots=True),
            "w1": frame_to_tab(weekly.tail(522), with_pivots=True),
            "mo1": frame_to_tab(mo[t].tail(300), with_pivots=True) if t in mo else None,  # 25y of months
        }
        d20 = daily.tail(20)
        facts = {"advol": round(float((d20["close"] * d20["volume"]).mean()), 0),
                 "vol_last": int(daily["volume"].iloc[-1])}
        if t in fu.index:
            f = fu.loc[t]
            def _g(k):
                v = f.get(k)
                return None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)
            facts.update({
                "mcap": _g("marketCap"), "pe": _g("trailingPE"), "fpe": _g("forwardPE"),
                "ps": _g("priceToSalesTrailing12Months"), "pm": _g("profitMargins"),
                "revg": _g("revenueGrowth"), "fcf": _g("freeCashflow"),
                "debt": _g("totalDebt"), "cash": _g("totalCash"), "beta": _g("beta"),
                "short": _g("shortPercentOfFloat"),
                "hi52": _g("fiftyTwoWeekHigh"), "lo52": _g("fiftyTwoWeekLow"),
            })
        payload = {
            "ticker": t,
            "group": UNIVERSE[t][0],
            "quality": UNIVERSE[t][1],
            "signal": signals.get(t, {}),
            "facts": facts,
            "tabs": {k: v for k, v in tabs.items() if v},
        }
        (out_dir / f"{t}.json").write_text(json.dumps(payload))
        n_ok += 1
    print(f"chart data: {n_ok}/{len(tickers)} symbols "
          f"(m5={len(m5)}, h1={len(h1)}, mo1={len(mo)})")


if __name__ == "__main__":
    main()
