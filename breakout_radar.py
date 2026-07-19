"""Breakout Radar — market-wide two-tier discovery screen (VBT-2).

Tier 1 — BOTTOM (early, Eric 2026-07-19): a stock that has bottomed with a
confirmed reversal on the weekly chart. Uses VBT-1's evidence-tested stage
engine (causal swing structure): weekly structure turns Uptrend while still
>=15% below the trailing 52-week peak, after a >=30% correction within the
last 26 weeks (stage 3, the only backtested signal with positive excess:
76% win, +25.3% median @26w). Fresh = the Uptrend transition happened this
week. These enter the WATCHLIST — entry candidates when the secular trend
confirms, otherwise followed until Tier 2.

Tier 2 — BREAKOUT (graduation): first weekly close >1% above the prior
52-week closing high after >=26 weeks without a new high.

Floors for both tiers: price >= $5, avg weekly dollar volume >= $25M,
market cap >= $1B (enriched via yfinance), QUALITY/SPEC tag
(profitable or FCF-positive, revenue growth >= 0).

State: radar_watch.json — the followed list. Names drop off when weekly
structure turns Downtrend again (DROP) or on breakout (GRADUATED).

Outputs (private repo): radar_latest.json, radar_watch.json,
radar_log.csv (append-only: every BOTTOM/BREAKOUT/DROP/GRADUATED event).

Runs weekly inside GitHub Actions (radar.yml). Runtime ~20 min.
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
LOOKBACK = 5           # weekly pivot lookback (same as VBT-1)
DD_ENTER = -0.30       # correction depth that arms the signal
DD_STILL_BELOW = -0.15 # must still be this far below peak at confirmation
MARGIN = 1.01          # breakout: close must exceed prior 52w high by 1%
BASE_WEEKS = 26        # breakout: min weeks since the last 52w high
MIN_PRICE = 5.0
MIN_WK_DOLLAR_VOL = 25e6
MIN_CAP = 1e9
CHUNK = 200


def get_symbols():
    """All US-listed common stocks from the Nasdaq Trader symbol directory."""
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    syms = []
    for u in urls:
        with urllib.request.urlopen(u, timeout=60) as r:
            text = r.read().decode()
        for row in csv.DictReader(io.StringIO(text), delimiter="|"):
            s = (row.get("Symbol") or row.get("ACT Symbol") or "").strip()
            if not s or "File Creation" in s:
                continue
            if row.get("ETF", "N") == "Y" or row.get("Test Issue", "N") == "Y":
                continue
            if any(c in s for c in "$.=+^~"):
                continue
            if len(s) == 5 and s[-1] in "WRUP":
                continue
            syms.append(s)
    syms = sorted(set(syms))
    print(f"symbol directory: {len(syms)} common-stock symbols")
    return syms


def causal_trend_history(high, low, lookback=LOOKBACK):
    """VBT-1's causal swing-structure engine (pivot effects delayed
    `lookback` bars so nothing uses future data)."""
    win = 2 * lookback + 1
    hp = (high == high.rolling(win, center=True).max()).fillna(False)
    lp = (low == low.rolling(win, center=True).min()).fillna(False)
    n, idx = len(high), high.index
    events = []
    for pos in range(n):
        if hp.iloc[pos]:
            events.append((pos + lookback, pos, "H"))
        if lp.iloc[pos]:
            events.append((pos + lookback, pos, "L"))
    events.sort()
    states, ei = [], 0
    last_h_val = last_l_val = last_h_lab = last_l_lab = None
    for j in range(n):
        while ei < len(events) and events[ei][0] <= j:
            _, ppos, kind = events[ei]
            ei += 1
            if kind == "H":
                v = float(high.iloc[ppos])
                if last_h_val is not None:
                    last_h_lab = "HH" if v > last_h_val else "LH"
                last_h_val = v
            else:
                v = float(low.iloc[ppos])
                if last_l_val is not None:
                    last_l_lab = "HL" if v > last_l_val else "LL"
                last_l_val = v
        states.append("Uptrend" if (last_h_lab, last_l_lab) == ("HH", "HL")
                      else "Downtrend" if (last_h_lab, last_l_lab) == ("LH", "LL")
                      else "Mixed")
    return pd.Series(states, index=idx)


def analyze(wk):
    """Per-symbol weekly analysis. wk = weekly OHLCV DataFrame (>=60 rows).
    Returns dict of current status + fresh-signal flags, or None."""
    if wk is None or len(wk) < 60:
        return None
    close, high, low, vol = wk["Close"], wk["High"], wk["Low"], wk["Volume"]
    cur = float(close.iloc[-1])
    if cur < MIN_PRICE:
        return None
    if float((close * vol).tail(13).mean()) < MIN_WK_DOLLAR_VOL:
        return None

    states = causal_trend_history(high, low)
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd_min26 = dd.rolling(26, min_periods=1).min()
    cur_state, cur_dd = str(states.iloc[-1]), float(dd.iloc[-1])
    corrected = bool(dd_min26.iloc[-1] <= DD_ENTER)
    fresh_up = cur_state == "Uptrend" and str(states.iloc[-2]) != "Uptrend"
    bottom = (corrected and cur_state == "Uptrend"
              and cur_dd <= DD_STILL_BELOW and fresh_up)

    prior = close.iloc[:-1]
    hi52 = float(prior.tail(52).max())
    hi_recent = float(prior.tail(BASE_WEEKS).max())
    breakout = cur > hi52 * MARGIN and hi_recent < hi52 * 0.999

    return {
        "close": round(cur, 2), "state": cur_state,
        "dd_pct": round(cur_dd * 100, 1),
        "max_dd_26w_pct": round(float(dd_min26.iloc[-1]) * 100, 1),
        "prior_52w_high": round(hi52, 2),
        "to_high_pct": round((hi52 / cur - 1) * 100, 1),
        "bottom": bottom, "breakout": breakout,
    }


def scan(symbols):
    """Batch-download 2y weekly OHLCV; return {ticker: analysis}."""
    results = {}
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        try:
            df = yf.download(batch, period="2y", interval="1wk",
                             group_by="ticker", threads=True,
                             progress=False, auto_adjust=True)
        except Exception as e:
            print(f"WARN batch {i}: {e}", file=sys.stderr)
            continue
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                r = analyze(sub)
                if r:
                    results[t] = r
            except Exception:
                continue
        if (i // CHUNK) % 5 == 0:
            print(f"scanned {i + len(batch)}/{len(symbols)}", flush=True)
    return results


def enrich(ticker):
    """Fundamentals for one hit; returns None if cap < $1B."""
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        print(f"WARN info {ticker}: {e}", file=sys.stderr)
        info = {}
    cap = info.get("marketCap") or 0
    if cap < MIN_CAP:
        return None
    pm, fcf, rg = (info.get("profitMargins"), info.get("freeCashflow"),
                   info.get("revenueGrowth"))
    quality = (((pm or 0) > 0 or (fcf or 0) > 0) and (rg is None or rg >= 0))
    return {
        "name": (info.get("shortName") or "").strip(),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "mkt_cap_B": round(cap / 1e9, 1),
        "pe": info.get("trailingPE"), "fwd_pe": info.get("forwardPE"),
        "rev_growth_pct": round(rg * 100, 1) if rg is not None else None,
        "profit_margin_pct": round(pm * 100, 1) if pm is not None else None,
        "fcf_B": round(fcf / 1e9, 2) if fcf else None,
        "tag": "QUALITY" if quality else "SPEC",
    }


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    watch_p = HERE / "radar_watch.json"
    watch = json.loads(watch_p.read_text()) if watch_p.exists() else {}

    symbols = get_symbols()
    results = scan(symbols)
    print(f"analyzed: {len(results)} symbols past liquidity floors")

    events = []  # (signal, ticker, analysis, fundamentals|None)

    # --- update existing watchlist first ---
    for t in list(watch):
        r = results.get(t)
        if r is None:
            watch[t]["status"] = "no-data"
            continue
        watch[t].update({"close": r["close"], "state": r["state"],
                         "dd_pct": r["dd_pct"], "to_high_pct": r["to_high_pct"],
                         "last_seen": today})
        if r["breakout"] or r["dd_pct"] >= -2.0:
            watch[t]["status"] = "graduated"
            events.append(("GRADUATED", t, r, None))
            del watch[t]
        elif r["state"] == "Downtrend":
            watch[t]["status"] = "dropped"
            events.append(("DROP", t, r, None))
            del watch[t]

    # --- new signals ---
    for t, r in results.items():
        if r["bottom"] and t not in watch:
            f = enrich(t)
            if f is None:
                continue
            events.append(("BOTTOM", t, r, f))
            watch[t] = {"added": today, "signal": "BOTTOM", "tag": f["tag"],
                        "name": f["name"], "sector": f["sector"],
                        "mkt_cap_B": f["mkt_cap_B"], "close": r["close"],
                        "state": r["state"], "dd_pct": r["dd_pct"],
                        "to_high_pct": r["to_high_pct"], "last_seen": today}
        elif r["breakout"]:
            f = enrich(t)
            if f is None:
                continue
            events.append(("BREAKOUT", t, r, f))

    watch_p.write_text(json.dumps(watch, indent=1))

    new_bottoms = [(t, r, f) for s, t, r, f in events if s == "BOTTOM"]
    new_breakouts = [(t, r, f) for s, t, r, f in events if s == "BREAKOUT"]

    (HERE / "radar_latest.json").write_text(json.dumps({
        "date": today,
        "criteria": {"bottom": "stage-3: Uptrend confirm, dd<=-15%, 26w max dd<=-30%",
                     "breakout": f"close > 52w high x{MARGIN}, base >= {BASE_WEEKS}w",
                     "min_cap_B": MIN_CAP / 1e9},
        "stats": {"symbols_in_directory": len(symbols),
                  "past_liquidity_floors": len(results),
                  "new_bottoms": len(new_bottoms),
                  "new_breakouts": len(new_breakouts),
                  "watchlist_size": len(watch)},
        "new_bottoms": [{**{"ticker": t}, **r, **(f or {})} for t, r, f in new_bottoms],
        "new_breakouts": [{**{"ticker": t}, **r, **(f or {})} for t, r, f in new_breakouts],
        "watchlist": watch,
    }, indent=1, default=str))

    logp = HERE / "radar_log.csv"
    fields = ["date", "signal", "ticker", "name", "tag", "close", "dd_pct",
              "max_dd_26w_pct", "to_high_pct", "prior_52w_high", "mkt_cap_B",
              "sector", "industry", "pe", "fwd_pe", "rev_growth_pct",
              "profit_margin_pct", "fcf_B"]
    new_file = not logp.exists()
    with open(logp, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for s, t, r, f in events:
            w.writerow({"date": today, "signal": s, "ticker": t, **r, **(f or {})})

    print(f"BOTTOM: {len(new_bottoms)}, BREAKOUT: {len(new_breakouts)}, "
          f"watchlist: {len(watch)}")
    for t, r, f in new_bottoms[:25]:
        print(f"  BOTTOM {f['tag']:7s} {t:6s} {f['name'][:26]:26s} "
              f"dd {r['dd_pct']}%  cap {f['mkt_cap_B']}B  "
              f"{r['to_high_pct']}% to 52w high")


if __name__ == "__main__":
    main()
