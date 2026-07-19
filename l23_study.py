"""L2/L3 re-entry lab (VBT-2 Phase 1, fourth study — Eric 2026-07-19).

Question: within an intact L1 uptrend, do base-resolution re-entries
(L2 weekly, L3 daily) add RETURN, or just turnover?

Regime: L1 intact = 13-week MA > 52-week MA (the adopted L1 workhorse
regime), measured weekly, causal.

Signals:
  L2 — weekly swing structure dips from Uptrend to Mixed and then
       freshly returns to Uptrend, all inside an intact L1 regime,
       without touching Downtrend in between.
  L3 — DAILY swing structure freshly turns Uptrend while the current
       weekly state is Uptrend and L1 is intact. (VBT-1's rule lab found
       daily entries had no edge in the correction-recovery context —
       here the context is an established uptrend; it must earn its
       place.)

Controls (the part that keeps us honest):
  C2 — ALL weeks with weekly state == Uptrend inside an intact L1
       regime, excluding fresh L2 weeks — "adding on any random week
       of the uptrend".
  C3 — ALL days with daily state == Uptrend (not fresh) in the same
       weekly context — the daily equivalent.

If L2 does not beat C2 (and L3 does not beat C3) on forward returns,
the re-entry signal is turnover, not timing.

Forward horizons: 13/26/52 weeks (65/130/260 trading days for daily).
Universe: thesis_universe.csv non-ETF names, 10y weekly + daily.
Outputs: l23_results.json, l23_events.csv (private repo).
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

CHUNK = 100
W_HORIZONS = (13, 26, 52)
D_HORIZONS = {13: 65, 26: 130, 52: 260}
CONTROL_STRIDE = 4  # sample every 4th control week/day to bound volume


def weekly_events(wk):
    """L2 events + C2 control weeks. Returns (l2_idx, c2_idx, close)."""
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    intact = (ma13 > ma52) & ma52.notna()
    l2, c2 = [], []
    dipped = False
    for j in range(56, len(wk)):
        if not bool(intact.iloc[j]):
            dipped = False
            continue
        st, prev = str(states.iloc[j]), str(states.iloc[j - 1])
        if st == "Downtrend":
            dipped = False
            continue
        if st == "Mixed" and prev == "Uptrend":
            dipped = True
        if st == "Uptrend":
            if prev != "Uptrend" and dipped:
                l2.append(j)
                dipped = False
            elif prev == "Uptrend":
                c2.append(j)
    return l2, c2[::CONTROL_STRIDE], close, states, intact


def daily_events(dl, wk_states, wk_intact, wk_index):
    """L3 events + C3 control days on daily bars, gated by weekly context."""
    close, high, low = dl["Close"], dl["High"], dl["Low"]
    dstates = causal_trend_history(high, low)
    # map each day to the most recent COMPLETED week
    wk_pos = wk_index.searchsorted(dl.index) - 1
    l3, c3 = [], []
    for j in range(30, len(dl)):
        wp = wk_pos[j]
        if wp < 56 or wp >= len(wk_index):
            continue
        if not (bool(wk_intact.iloc[wp]) and str(wk_states.iloc[wp]) == "Uptrend"):
            continue
        st, prev = str(dstates.iloc[j]), str(dstates.iloc[j - 1])
        if st == "Uptrend" and prev != "Uptrend":
            l3.append(j)
        elif st == "Uptrend":
            c3.append(j)
    return l3, c3[::CONTROL_STRIDE], close


def fwd(close, j, n):
    if j + n < len(close):
        return round((float(close.iloc[j + n]) / float(close.iloc[j]) - 1) * 100, 1)
    return None


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    tickers = [r["ticker"] for r in rows if r["theme"] != "etf"]

    events = []
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        dfw = yf.download(batch, period="10y", interval="1wk",
                          group_by="ticker", threads=True,
                          progress=False, auto_adjust=True)
        dfd = yf.download(batch, period="10y", interval="1d",
                          group_by="ticker", threads=True,
                          progress=False, auto_adjust=True)
        for t in batch:
            try:
                wk = dfw[t].dropna() if len(batch) > 1 else dfw.dropna()
                dl = dfd[t].dropna() if len(batch) > 1 else dfd.dropna()
                if len(wk) < 110 or len(dl) < 300:
                    continue
                l2, c2, wclose, wstates, wintact = weekly_events(wk)
                for kind, idxs in (("L2", l2), ("C2", c2)):
                    for j in idxs:
                        rec = {"ticker": t, "kind": kind,
                               "date": wk.index[j].date().isoformat()}
                        for h in W_HORIZONS:
                            rec[f"fwd{h}w"] = fwd(wclose, j, h)
                        events.append(rec)
                l3, c3, dclose = daily_events(dl, wstates, wintact, wk.index)
                for kind, idxs in (("L3", l3), ("C3", c3)):
                    for j in idxs:
                        rec = {"ticker": t, "kind": kind,
                               "date": dl.index[j].date().isoformat()}
                        for h, nd in D_HORIZONS.items():
                            rec[f"fwd{h}w"] = fwd(dclose, j, nd)
                        events.append(rec)
            except Exception as e:
                print(f"WARN {t}: {e}", file=sys.stderr)
        print(f"processed {min(i + CHUNK, len(tickers))}/{len(tickers)}, "
              f"events {len(events)}", flush=True)

    def agg(evs, key):
        v = sorted(e[key] for e in evs if e.get(key) is not None)
        if not v:
            return None
        n = len(v)
        return {"n": n, "median": round(v[n // 2], 1),
                "mean": round(sum(v) / n, 1),
                "win_rate": round(sum(1 for x in v if x > 0) / n * 100, 1)}

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "control_stride": CONTROL_STRIDE}
    for kind in ("L2", "C2", "L3", "C3"):
        ev = [e for e in events if e["kind"] == kind]
        nt = len({e["ticker"] for e in ev})
        results[kind] = {"events": len(ev), "names": nt,
                         **{f"fwd{h}w": agg(ev, f"fwd{h}w")
                            for h in W_HORIZONS}}

    (HERE / "l23_results.json").write_text(json.dumps(results, indent=1))
    fields = ["ticker", "kind", "date", "fwd13w", "fwd26w", "fwd52w"]
    with open(HERE / "l23_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
