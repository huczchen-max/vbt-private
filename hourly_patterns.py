"""Eric's hourly pattern test (VBT-2 Phase 4; 2026-07-19).

Within up(W)-up(D) regimes, test Eric's EXACT three-pivot hourly
patterns as long-option triggers, split by trend character:

  TOP    — last three hourly HIGH pivots labeled [HH, LH, LH]
           (trigger at causal confirmation of the second LH)
           -> proposed: buy put
  BOTTOM — last three hourly LOW pivots labeled [LL, HL, HL]
           -> proposed: buy call

Trend character per day (causal): PARABOLIC if the daily close's
extension above its 50-day MA is in the top decile of its own expanding
history (>=100 prior days), else NORMAL. Only BULL days (weekly 13/52w
intact AND daily structure Uptrend) are analyzed.

Metrics per event vs in-regime controls: forward 7/21/35 hourly-bar
returns; P(move <= -2%) within 3d (what a put needs) and P(move >= +2%)
(what a call needs) — 2% approximates a 3-day ATM premium at IV ~50.

Outputs: hpat_results.json, hpat_events.csv (private).
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
LOOKBACK = 5
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


def pivot_labels(high, low, lookback=LOOKBACK):
    """Causal pivot stream: list of (confirm_pos, kind 'H'|'L', label)."""
    win = 2 * lookback + 1
    hp = (high == high.rolling(win, center=True).max()).fillna(False)
    lp = (low == low.rolling(win, center=True).min()).fillna(False)
    events = []
    for pos in range(len(high)):
        if hp.iloc[pos]:
            events.append((pos + lookback, pos, "H"))
        if lp.iloc[pos]:
            events.append((pos + lookback, pos, "L"))
    events.sort()
    out = []
    last = {"H": None, "L": None}
    for conf, pos, kind in events:
        v = float(high.iloc[pos]) if kind == "H" else float(low.iloc[pos])
        lab = None
        if last[kind] is not None:
            if kind == "H":
                lab = "HH" if v > last[kind] else "LH"
            else:
                lab = "HL" if v > last[kind] else "LL"
        last[kind] = v
        if lab:
            out.append((conf, kind, lab))
    return out


def daily_context(hr):
    """Per-date: in-BULL flag and PARABOLIC flag (both causal)."""
    daily = hr.resample("1D").agg({"Open": "first", "High": "max",
                                   "Low": "min", "Close": "last"}).dropna()
    weekly = daily.resample("W-FRI").agg({"High": "max", "Low": "min",
                                          "Close": "last"}).dropna()
    dstates = causal_trend_history(daily["High"], daily["Low"])
    wma13 = weekly["Close"].rolling(13).mean()
    wma52 = weekly["Close"].rolling(52).mean()
    wintact = (wma13 > wma52) & wma52.notna()
    wk_pos = weekly.index.searchsorted(daily.index) - 1
    ma50 = daily["Close"].rolling(50).mean()
    ext = daily["Close"] / ma50 - 1
    ctx = {}
    ext_hist = []
    for i, d in enumerate(daily.index):
        wp = wk_pos[i]
        intact = bool(wintact.iloc[wp]) if 0 <= wp < len(weekly) else False
        ds = str(dstates.iloc[i])
        if intact and ds == "Uptrend":
            regime = "BULL"
        elif not intact and ds == "Downtrend":
            regime = "BEAR"
        else:
            regime = None
        e = ext.iloc[i]
        char = "NORMAL"
        if pd.notna(e):
            if len(ext_hist) >= 100:
                rank = sum(1 for x in ext_hist if x < e) / len(ext_hist)
                if regime == "BULL" and rank >= 0.90 and e > 0:
                    char = "PARABOLIC"
                elif regime == "BEAR" and rank <= 0.10 and e < 0:
                    char = "CAPITULATIVE"
            ext_hist.append(float(e))
        ctx[d.date()] = (regime, char)
    return ctx


def main():
    syms = universe()
    print(f"universe: {len(syms)}")
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
                ctx = daily_context(hr)
                close = hr["Close"]
                n = len(hr)
                piv = pivot_labels(hr["High"], hr["Low"])
                highs, lows = [], []
                trig = {}  # bar index -> pattern
                for conf, kind, lab in piv:
                    if conf >= n:
                        continue
                    if kind == "H":
                        highs.append(lab)
                        if highs[-3:] == ["HH", "LH", "LH"]:
                            trig[conf] = "TOP"
                    else:
                        lows.append(lab)
                        if lows[-3:] == ["LL", "HL", "HL"]:
                            trig[conf] = "BOTTOM"
                for j in range(60, n):
                    c = ctx.get(hr.index[j].date())
                    if not c or c[0] is None:
                        continue  # BULL or BEAR days only
                    regime, char = c
                    kind = trig.get(j)
                    if kind is None:
                        if j % CONTROL_STRIDE == 0:
                            kind = "CTRL"
                        else:
                            continue
                    rec = {"ticker": t, "kind": kind,
                           "regime": regime, "char": char,
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
        if len(v) < 25:
            return None
        n = len(v)
        return {"n": n, "median": round(v[n // 2], 3),
                "mean": round(sum(v) / n, 3),
                "win_rate": round(sum(1 for x in v if x > 0) / n * 100, 1),
                "p_le_m2": round(sum(1 for x in v if x <= -2) / n * 100, 1),
                "p_ge_2": round(sum(1 for x in v if x >= 2) / n * 100, 1)}

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "definitions": {"TOP": "high pivots [HH,LH,LH] -> proposed buy put",
                               "BOTTOM": "low pivots [LL,HL,HL] -> proposed buy call",
                               "PARABOLIC": "daily ext over 50d MA in top decile "
                                            "of own expanding history"}}
    for regime, char in (("BULL", "NORMAL"), ("BULL", "PARABOLIC"),
                         ("BEAR", "NORMAL"), ("BEAR", "CAPITULATIVE")):
        block = {}
        for kind in ("TOP", "BOTTOM", "CTRL"):
            ev = [e for e in events if e.get("regime") == regime
                  and e["char"] == char and e["kind"] == kind]
            block[kind] = {lab: agg(ev, f"fwd{lab}") for lab in HORIZONS}
            block[kind]["events"] = len(ev)
        results[f"{regime}/{char}"] = block
    (HERE / "hpat_results.json").write_text(json.dumps(results, indent=1))
    with open(HERE / "hpat_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "kind", "regime", "char",
                                          "dt", "fwd1d", "fwd3d", "fwd5d"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    keys = ["BULL/NORMAL", "BULL/PARABOLIC", "BEAR/NORMAL",
            "BEAR/CAPITULATIVE"]
    print(json.dumps({c: {k: results[c][k].get("3d")
                          for k in ("TOP", "BOTTOM", "CTRL")}
                      for c in keys}, indent=1))


if __name__ == "__main__":
    main()
