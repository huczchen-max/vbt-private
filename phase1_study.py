"""Phase 1 study — does entering at BOTTOM beat waiting for BREAKOUT,
market-wide? (VBT-2, Eric 2026-07-19)

Universe: all currently-listed US common stocks passing the radar's
liquidity floors (price >= $5, avg weekly $vol >= $25M) — survivorship
bias acknowledged: this is today's survivor list, so absolute numbers are
optimistic ceilings; the BOTTOM-vs-BREAKOUT COMPARISON is the point.

Signals (identical definitions to breakout_radar.py):
  BOTTOM   — weekly structure freshly turns Uptrend while >=15% below the
             trailing 52w peak, after a >=30% correction within 26 weeks.
  BREAKOUT — first weekly close >1% above the prior 52w closing high
             after >=26 weeks without a new high.

Measured per event: forward 13/26/52-week returns, 26w MAE, excess vs SPY.
Paired analysis: for each BOTTOM, the first BREAKOUT within 52w in the
same name — the "head start" of entering early vs waiting; plus the
failure rate of bottoms that never graduate.

Outputs (private repo): phase1_events.csv, phase1_results.json.
Runs inside GitHub Actions (phase1.yml). Runtime ~25 min.
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
from breakout_radar import (get_symbols, causal_trend_history,  # noqa: E402
                            LOOKBACK, DD_ENTER, DD_STILL_BELOW, MARGIN,
                            BASE_WEEKS, MIN_PRICE, MIN_WK_DOLLAR_VOL)

CHUNK = 200
HORIZONS = (13, 26, 52)


def weekly_events(wk):
    """All BOTTOM and BREAKOUT events for one symbol's weekly OHLCV."""
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd26 = dd.rolling(26, min_periods=1).min()
    events = []
    for j in range(60, len(wk)):
        fresh_up = (str(states.iloc[j]) == "Uptrend"
                    and str(states.iloc[j - 1]) != "Uptrend")
        if (fresh_up and float(dd.iloc[j]) <= DD_STILL_BELOW
                and float(dd26.iloc[j]) <= DD_ENTER):
            events.append(("BOTTOM", j))
        prior = close.iloc[:j]
        hi52 = float(prior.tail(52).max())
        hi_recent = float(prior.tail(BASE_WEEKS).max())
        if (float(close.iloc[j]) > hi52 * MARGIN
                and hi_recent < hi52 * 0.999):
            events.append(("BREAKOUT", j))
    return events, close


def fwd_metrics(close, j, spy_close, dates):
    """Forward returns, MAE, and SPY excess from week j."""
    out = {}
    p0 = float(close.iloc[j])
    d0 = dates[j]
    for h in HORIZONS:
        if j + h < len(close):
            r = float(close.iloc[j + h]) / p0 - 1
            out[f"fwd{h}w"] = round(r * 100, 1)
            s = spy_close.reindex([d0, dates[j + h]], method="nearest")
            out[f"exc{h}w"] = round((r - (float(s.iloc[1]) / float(s.iloc[0]) - 1)) * 100, 1)
    if j + 1 < len(close):
        w = close.iloc[j:min(j + 27, len(close))]
        out["mae26w"] = round((float(w.min()) / p0 - 1) * 100, 1)
    return out


def main():
    spy = yf.download("SPY", period="12y", interval="1wk",
                      progress=False, auto_adjust=True)
    spy_close = spy["Close"].squeeze()

    symbols = get_symbols()
    all_events = []
    n_liquid = 0
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        try:
            df = yf.download(batch, period="10y", interval="1wk",
                             group_by="ticker", threads=True,
                             progress=False, auto_adjust=True)
        except Exception as e:
            print(f"WARN batch {i}: {e}", file=sys.stderr)
            continue
        for t in batch:
            try:
                wk = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(wk) < 61:
                    continue
                if float(wk["Close"].iloc[-1]) < MIN_PRICE:
                    continue
                if float((wk["Close"] * wk["Volume"]).tail(13).mean()) < MIN_WK_DOLLAR_VOL:
                    continue
                n_liquid += 1
                events, close = weekly_events(wk)
                dates = wk.index
                for kind, j in events:
                    rec = {"ticker": t, "signal": kind,
                           "date": dates[j].date().isoformat(),
                           "price": round(float(close.iloc[j]), 2)}
                    rec.update(fwd_metrics(close, j, spy_close, dates))
                    all_events.append(rec)
            except Exception:
                continue
        if (i // CHUNK) % 5 == 0:
            print(f"scanned {i + len(batch)}/{len(symbols)}, "
                  f"events {len(all_events)}", flush=True)

    # ---- pairing: each BOTTOM -> first BREAKOUT in same name within 52w
    by_tkr = {}
    for e in all_events:
        by_tkr.setdefault(e["ticker"], []).append(e)
    pairs, orphans = [], []
    for t, evs in by_tkr.items():
        evs.sort(key=lambda e: e["date"])
        bks = [e for e in evs if e["signal"] == "BREAKOUT"]
        for b in [e for e in evs if e["signal"] == "BOTTOM"]:
            b_date = pd.Timestamp(b["date"])
            nxt = next((k for k in bks
                        if 0 < (pd.Timestamp(k["date"]) - b_date).days <= 370), None)
            if nxt:
                pairs.append({
                    "ticker": t, "bottom_date": b["date"],
                    "breakout_date": nxt["date"],
                    "weeks_to_breakout": round(
                        (pd.Timestamp(nxt["date"]) - b_date).days / 7, 1),
                    "head_start_pct": round(
                        (nxt["price"] / b["price"] - 1) * 100, 1),
                    "bottom_fwd26w": b.get("fwd26w"),
                    "breakout_fwd26w": nxt.get("fwd26w"),
                })
            else:
                orphans.append(b)

    def agg(evs, key):
        vals = sorted(e[key] for e in evs if e.get(key) is not None)
        if not vals:
            return None
        n = len(vals)
        return {"n": n, "median": vals[n // 2],
                "mean": round(sum(vals) / n, 1),
                "win_rate": round(sum(1 for v in vals if v > 0) / n * 100, 1)}

    bots = [e for e in all_events if e["signal"] == "BOTTOM"]
    brks = [e for e in all_events if e["signal"] == "BREAKOUT"]
    results = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": {"symbols_scanned": len(symbols), "liquid": n_liquid,
                     "note": "survivorship-biased (today's listings); "
                             "comparison, not absolute levels, is the finding"},
        "events": {"BOTTOM": len(bots), "BREAKOUT": len(brks)},
        "BOTTOM": {k: agg(bots, k) for k in
                   ["fwd13w", "fwd26w", "fwd52w", "exc26w", "exc52w", "mae26w"]},
        "BREAKOUT": {k: agg(brks, k) for k in
                     ["fwd13w", "fwd26w", "fwd52w", "exc26w", "exc52w", "mae26w"]},
        "pairs": {
            "n_paired": len(pairs),
            "n_bottom_never_graduated_1y": len(orphans),
            "graduation_rate_pct": round(
                len(pairs) / max(1, len(pairs) + len(orphans)) * 100, 1),
            "weeks_to_breakout": agg(pairs, "weeks_to_breakout"),
            "head_start_pct": agg(pairs, "head_start_pct"),
            "orphan_bottom_fwd26w": agg(orphans, "fwd26w"),
        },
    }

    (HERE / "phase1_results.json").write_text(json.dumps(results, indent=1))
    fields = ["ticker", "signal", "date", "price", "fwd13w", "fwd26w",
              "fwd52w", "exc13w", "exc26w", "exc52w", "mae26w"]
    with open(HERE / "phase1_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_events)
    with open(HERE / "phase1_pairs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0].keys()) if pairs else ["x"])
        w.writeheader()
        w.writerows(pairs)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
