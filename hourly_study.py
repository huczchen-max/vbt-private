"""Phase 4b — hourly drift study by regime (VBT-2; Eric 2026-07-19).

Question: conditional on the weekly/daily regime, does HOURLY swing
structure predict short-term drift at all? Two hypotheses, tested
separately because they serve different masters:
  H1 PREDICTION — a fresh hourly Uptrend transition predicts positive
     forward drift beyond the regime baseline (would justify hourly
     directional entries).
  H2 DEFENSE    — a fresh hourly Downtrend transition INSIDE a bull
     regime predicts negative forward drift (would justify using hourly
     as a tripwire to tighten/close short-premium positions).

Regimes (daily resolution, causal, from our standard engines):
  BULL  — weekly 13w/52w MA intact AND daily structure Uptrend
  BEAR  — weekly broken AND daily structure Downtrend
  RANGE — everything else
Controls: every 6th in-regime hour (excluding event hours' effect is
approximated by the sheer control mass).

Universe: benchmark ETFs + winner-screen top-5 per theme (~40 symbols —
the set the options program would actually trade).
Data: yfinance hourly, 730 days (its maximum — a 2-year window covering
one bull leg and one correction; limitation noted in output).
Forward horizons: 7 / 21 / 35 hourly bars (~1 / 3 / 5 trading days).

Outputs: hourly_results.json, hourly_events.csv (private).
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
from breakout_radar import causal_trend_history  # noqa: E402

ETFS = ["SPY", "QQQ", "SMH", "GRID", "BOTZ", "ITA", "XLV"]
TOP_N = 5
HORIZONS = {"1d": 7, "3d": 21, "5d": 35}
CONTROL_STRIDE = 6
CHUNK = 20


def universe():
    syms = list(ETFS)
    try:
        w = json.loads((HERE / "winners.json").read_text())
        for ranked in w.get("themes", {}).values():
            for r in ranked[:TOP_N]:
                if r["ticker"] not in syms:
                    syms.append(r["ticker"])
    except Exception as e:
        print(f"WARN winners.json: {e}", file=sys.stderr)
    return syms


def daily_regimes(hr):
    """Regime per calendar date from daily/weekly resamples of the
    hourly frame (causal)."""
    daily = hr.resample("1D").agg({"Open": "first", "High": "max",
                                   "Low": "min", "Close": "last"}).dropna()
    weekly = daily.resample("W-FRI").agg({"Open": "first", "High": "max",
                                          "Low": "min", "Close": "last"}).dropna()
    dstates = causal_trend_history(daily["High"], daily["Low"])
    wma13 = weekly["Close"].rolling(13).mean()
    wma52 = weekly["Close"].rolling(52).mean()
    wintact = (wma13 > wma52) & wma52.notna()
    # map each date to the most recent completed week
    wk_pos = weekly.index.searchsorted(daily.index) - 1
    regimes = {}
    for i, d in enumerate(daily.index):
        wp = wk_pos[i]
        intact = bool(wintact.iloc[wp]) if 0 <= wp < len(weekly) else False
        ds = str(dstates.iloc[i])
        if intact and ds == "Uptrend":
            reg = "BULL"
        elif not intact and ds == "Downtrend":
            reg = "BEAR"
        else:
            reg = "RANGE"
        regimes[d.date()] = reg
    return regimes


def main():
    syms = universe()
    print(f"universe: {len(syms)} symbols")
    events = []
    for i in range(0, len(syms), CHUNK):
        batch = syms[i:i + CHUNK]
        try:
            df = yf.download(batch, period="730d", interval="1h",
                             group_by="ticker", threads=True,
                             progress=False, auto_adjust=True)
        except Exception as e:
            print(f"WARN batch {i}: {e}", file=sys.stderr)
            continue
        for t in batch:
            try:
                hr = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(hr) < 800:
                    continue
                hr = hr.tz_localize(None) if hr.index.tz is not None else hr
                regimes = daily_regimes(hr)
                hstates = causal_trend_history(hr["High"], hr["Low"])
                close = hr["Close"]
                n = len(hr)
                for j in range(60, n):
                    reg = regimes.get(hr.index[j].date())
                    if reg is None:
                        continue
                    st, prev = str(hstates.iloc[j]), str(hstates.iloc[j - 1])
                    kind = None
                    if st == "Uptrend" and prev != "Uptrend":
                        kind = "H_UP"
                    elif st == "Downtrend" and prev != "Downtrend":
                        kind = "H_DOWN"
                    elif j % CONTROL_STRIDE == 0:
                        kind = "CTRL"
                    if kind is None:
                        continue
                    rec = {"ticker": t, "regime": reg, "kind": kind,
                           "dt": hr.index[j].isoformat()}
                    p0 = float(close.iloc[j])
                    for lab, h in HORIZONS.items():
                        if j + h < n:
                            rec[f"fwd{lab}"] = round(
                                (float(close.iloc[j + h]) / p0 - 1) * 100, 3)
                    events.append(rec)
            except Exception as e:
                print(f"WARN {t}: {e}", file=sys.stderr)
        print(f"processed {min(i + CHUNK, len(syms))}/{len(syms)}, "
              f"events {len(events)}", flush=True)

    def agg(evs, key):
        v = sorted(e[key] for e in evs if e.get(key) is not None)
        if len(v) < 30:
            return None
        n = len(v)
        return {"n": n, "median": round(v[n // 2], 3),
                "mean": round(sum(v) / n, 3),
                "win_rate": round(sum(1 for x in v if x > 0) / n * 100, 1)}

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "note": "730-day window (yfinance hourly max) — one bull leg "
                       "+ one correction; go/no-go gate, not a full history",
               "universe": len(syms)}
    for reg in ("BULL", "RANGE", "BEAR"):
        block = {}
        for kind in ("H_UP", "H_DOWN", "CTRL"):
            ev = [e for e in events if e["regime"] == reg and e["kind"] == kind]
            block[kind] = {lab: agg(ev, f"fwd{lab}") for lab in HORIZONS}
            block[kind]["events"] = len(ev)
        results[reg] = block

    (HERE / "hourly_results.json").write_text(json.dumps(results, indent=1))
    fields = ["ticker", "regime", "kind", "dt", "fwd1d", "fwd3d", "fwd5d"]
    with open(HERE / "hourly_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    print(json.dumps({r: {k: results[r][k].get("3d")
                          for k in ("H_UP", "H_DOWN", "CTRL")}
                      for r in ("BULL", "RANGE", "BEAR")}, indent=1))


if __name__ == "__main__":
    main()
