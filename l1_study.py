"""L1 lab — three-way test of the secular-entry signal on the thesis
universe (VBT-2 Phase 1; decisions Eric 2026-07-19).

Definitions tested per name (weekly bars, 10y):
  BOTTOM  — fresh causal-structure Uptrend confirm >=15% below the 52w
            peak after a >=30% correction in 26w (VBT-1 stage 3).
  BRKOUT  — first weekly close >1% above the prior 52w closing high
            after >=26 weeks without a new high (definitive base breakout).
  MACROSS — 13-week MA freshly crosses above the 52-week MA.

Scoring (Eric: capture + low whipsaw beats max return; theme-ETF
buy-and-hold is the null):
  - forward 26/52/104-week returns, 52w MAE
  - excess vs the THEME BENCHMARK ETF over the same window (and vs SPY)
  - signals per name (whipsaw), median weeks between signals
  - CAPTURE: for each name's FIRST signal, the fraction of the name's
    total 10y move that came after the signal (only for names whose
    total return > +25%, where "capturing the move" is meaningful).

Universe: thesis_universe.csv. Theme -> benchmark: ai=SMH grid=GRID
robotics=BOTZ defense=ITA health=XLV outlier=QQQ etf=SPY.

Outputs (private repo): l1_results.json, l1_events.csv.
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from breakout_radar import (causal_trend_history, DD_ENTER,  # noqa: E402
                            DD_STILL_BELOW, MARGIN, BASE_WEEKS)

BENCH = {"ai": "SMH", "grid": "GRID", "robotics": "BOTZ",
         "defense": "ITA", "health": "XLV", "outlier": "QQQ", "etf": "SPY"}
HORIZONS = (26, 52, 104)
CHUNK = 100


def signals_for(wk):
    """Return {definition: [week-index, ...]} for one symbol."""
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd26 = dd.rolling(26, min_periods=1).min()
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    out = {"BOTTOM": [], "BRKOUT": [], "MACROSS": []}
    for j in range(56, len(wk)):
        if (str(states.iloc[j]) == "Uptrend"
                and str(states.iloc[j - 1]) != "Uptrend"
                and float(dd.iloc[j]) <= DD_STILL_BELOW
                and float(dd26.iloc[j]) <= DD_ENTER):
            out["BOTTOM"].append(j)
        prior = close.iloc[:j]
        hi52 = float(prior.tail(52).max())
        if (float(close.iloc[j]) > hi52 * MARGIN
                and float(prior.tail(BASE_WEEKS).max()) < hi52 * 0.999):
            out["BRKOUT"].append(j)
        if (pd.notna(ma52.iloc[j]) and pd.notna(ma52.iloc[j - 1])
                and float(ma13.iloc[j]) > float(ma52.iloc[j])
                and float(ma13.iloc[j - 1]) <= float(ma52.iloc[j - 1])):
            out["MACROSS"].append(j)
    return out


def window_ret(series, d0, d1):
    s = series.reindex([d0, d1], method="nearest")
    try:
        return float(s.iloc[1]) / float(s.iloc[0]) - 1
    except Exception:
        return None


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    names = [(r["ticker"], r["theme"]) for r in rows if r["theme"] != "etf"]
    bench_syms = sorted(set(BENCH.values()))

    bench = {}
    for b in bench_syms:
        d = yf.download(b, period="10y", interval="1wk",
                        progress=False, auto_adjust=True)
        bench[b] = d["Close"].squeeze()

    tickers = [t for t, _ in names]
    data = {}
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        df = yf.download(batch, period="10y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(sub) >= 80:
                    data[t] = sub
            except Exception:
                continue
        print(f"downloaded {min(i + CHUNK, len(tickers))}/{len(tickers)}",
              flush=True)

    theme_of = dict(names)
    events, per_name = [], []
    for t, wk in data.items():
        theme = theme_of[t]
        bser = bench[BENCH[theme]]
        spy = bench["SPY"]
        close = wk["Close"]
        dates = wk.index
        sigs = signals_for(wk)
        total_ret = float(close.iloc[-1]) / float(close.iloc[0]) - 1
        yrs = (dates[-1] - dates[0]).days / 365.25
        for defn, idxs in sigs.items():
            for j in idxs:
                p0, d0 = float(close.iloc[j]), dates[j]
                rec = {"ticker": t, "theme": theme, "defn": defn,
                       "date": d0.date().isoformat(), "price": round(p0, 2)}
                for h in HORIZONS:
                    if j + h < len(close):
                        r = float(close.iloc[j + h]) / p0 - 1
                        rec[f"fwd{h}w"] = round(r * 100, 1)
                        rb = window_ret(bser, d0, dates[j + h])
                        rs = window_ret(spy, d0, dates[j + h])
                        if rb is not None:
                            rec[f"excB{h}w"] = round((r - rb) * 100, 1)
                        if rs is not None:
                            rec[f"excS{h}w"] = round((r - rs) * 100, 1)
                w = close.iloc[j:min(j + 53, len(close))]
                rec["mae52w"] = round((float(w.min()) / p0 - 1) * 100, 1)
                events.append(rec)
            # per-name stats
            nm = {"ticker": t, "theme": theme, "defn": defn,
                  "n_signals": len(idxs),
                  "sig_per_yr": round(len(idxs) / max(yrs, 1), 2)}
            if idxs and total_ret > 0.25:
                j0 = idxs[0]
                after = float(close.iloc[-1]) / float(close.iloc[j0]) - 1
                nm["capture_pct"] = round(
                    max(-100.0, min(200.0, after / total_ret * 100)), 1)
                # null: theme-ETF hold from the same first-signal date
                rb = window_ret(bser, dates[j0], dates[-1])
                if rb is not None:
                    nm["first_sig_vs_etf_pct"] = round((after - rb) * 100, 1)
            per_name.append(nm)

    def agg(vals):
        v = sorted(x for x in vals if x is not None)
        if not v:
            return None
        n = len(v)
        return {"n": n, "median": round(v[n // 2], 1),
                "mean": round(sum(v) / n, 1),
                "win_rate": round(sum(1 for x in v if x > 0) / n * 100, 1)}

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "names_with_data": len(data)}
    for defn in ("BOTTOM", "BRKOUT", "MACROSS"):
        ev = [e for e in events if e["defn"] == defn]
        pn = [p for p in per_name if p["defn"] == defn]
        results[defn] = {
            "events": len(ev),
            "names_with_signal": sum(1 for p in pn if p["n_signals"] > 0),
            "signals_per_name_yr": agg([p["sig_per_yr"] for p in pn
                                        if p["n_signals"] > 0]),
            **{f"fwd{h}w": agg([e.get(f"fwd{h}w") for e in ev])
               for h in HORIZONS},
            **{f"excB{h}w": agg([e.get(f"excB{h}w") for e in ev])
               for h in HORIZONS},
            "excS52w": agg([e.get("excS52w") for e in ev]),
            "mae52w": agg([e.get("mae52w") for e in ev]),
            "capture_pct": agg([p.get("capture_pct") for p in pn]),
            "first_sig_vs_etf_pct": agg([p.get("first_sig_vs_etf_pct")
                                         for p in pn]),
        }

    (HERE / "l1_results.json").write_text(json.dumps(results, indent=1))
    fields = ["ticker", "theme", "defn", "date", "price",
              "fwd26w", "fwd52w", "fwd104w", "excB26w", "excB52w",
              "excB104w", "excS26w", "excS52w", "excS104w", "mae52w"]
    with open(HERE / "l1_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
