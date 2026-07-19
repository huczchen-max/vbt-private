"""Exit-vs-hold lab (VBT-2 Phase 1, third study — Eric 2026-07-19).

Question: after an L1 entry, does ANY exit rule beat holding through,
after whipsaw costs? The stated purpose of exits is avoiding MAJOR
drawdowns — so the scoreboard is (terminal wealth vs hold) x (equity-curve
max-drawdown reduction).

Per name (10y weekly): enter at the FIRST L1 signal (fresh 13w/52w MA
cross [MACROSS] or confirmed deep-correction bottom [BOTTOM] — the
adopted L1 doors). Then:
  HOLD — stay invested to the end (the null).
  X1 STRUCT   — exit while weekly causal structure == Downtrend.
  X2 MA52     — exit while weekly close < 52-week MA.
  X3 CROSSDN  — exit on 13w/52w MA cross-down (symmetric to entry).
  X4 TRAIL25  — exit when close is >=25% below the post-entry peak;
                re-entry via L1 doors only.
  X5 COMBO    — exit only when structure == Downtrend AND close < MA52
                (the plan's original candidate).
Re-entry for all rules: next fresh MACROSS or BOTTOM signal (plus, for
X2/X3, the natural re-cross condition is intentionally NOT used — the
ladder as designed re-enters through L1 doors only).

Execution at the signal week's close. Cash yields 0% (biases AGAINST
exit rules — a rule that still wins is robust).

Outputs: exit_results.json, exit_per_name.csv (private repo).
Universe: thesis_universe.csv names + the theme ETFs as a separate,
less-survivorship-biased group.
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
                            DD_STILL_BELOW)

CHUNK = 100
RULES = ("HOLD", "X1_STRUCT", "X2_MA52", "X3_CROSSDN", "X4_TRAIL25",
         "X5_COMBO")


def prep(wk):
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd26 = dd.rolling(26, min_periods=1).min()
    entry = []
    for j in range(56, len(wk)):
        mac = (pd.notna(ma52.iloc[j]) and pd.notna(ma52.iloc[j - 1])
               and float(ma13.iloc[j]) > float(ma52.iloc[j])
               and float(ma13.iloc[j - 1]) <= float(ma52.iloc[j - 1]))
        bot = (str(states.iloc[j]) == "Uptrend"
               and str(states.iloc[j - 1]) != "Uptrend"
               and float(dd.iloc[j]) <= DD_STILL_BELOW
               and float(dd26.iloc[j]) <= DD_ENTER)
        entry.append(mac or bot)
    entry = pd.Series([False] * 56 + entry, index=wk.index)
    return close, states, ma13, ma52, entry


def maxdd(curve):
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def simulate(close, states, ma13, ma52, entry, rule):
    """Equity curve from first entry signal to end. Returns metrics."""
    idxs = [i for i, e in enumerate(entry) if e]
    if not idxs:
        return None
    start = idxs[0]
    invested = True
    eq = [1.0]
    peak_px = float(close.iloc[start])
    trades = 1
    weeks_in = 0
    for j in range(start + 1, len(close)):
        px, prev = float(close.iloc[j]), float(close.iloc[j - 1])
        if invested:
            eq.append(eq[-1] * px / prev)
            weeks_in += 1
            peak_px = max(peak_px, px)
        else:
            eq.append(eq[-1])
        if rule == "HOLD":
            continue
        if invested:
            st = str(states.iloc[j])
            below = pd.notna(ma52.iloc[j]) and px < float(ma52.iloc[j])
            crossdn = (pd.notna(ma52.iloc[j]) and pd.notna(ma52.iloc[j - 1])
                       and float(ma13.iloc[j]) < float(ma52.iloc[j])
                       and float(ma13.iloc[j - 1]) >= float(ma52.iloc[j - 1]))
            out = ((rule == "X1_STRUCT" and st == "Downtrend")
                   or (rule == "X2_MA52" and below)
                   or (rule == "X3_CROSSDN" and crossdn)
                   or (rule == "X4_TRAIL25" and px <= peak_px * 0.75)
                   or (rule == "X5_COMBO" and st == "Downtrend" and below))
            if out:
                invested = False
        else:
            if bool(entry.iloc[j]):
                invested = True
                peak_px = px
                trades += 1
    n = len(eq)
    return {"terminal": eq[-1], "maxdd": maxdd(eq), "trades": trades,
            "pct_invested": round(weeks_in / max(1, n - 1) * 100, 1)}


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    tickers = [(r["ticker"], r["theme"]) for r in rows]
    data = {}
    tl = [t for t, _ in tickers]
    for i in range(0, len(tl), CHUNK):
        batch = tl[i:i + CHUNK]
        df = yf.download(batch, period="10y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(sub) >= 110:
                    data[t] = sub
            except Exception:
                continue
        print(f"downloaded {min(i + CHUNK, len(tl))}/{len(tl)}", flush=True)

    theme_of = dict(tickers)
    per_name = []
    for t, wk in data.items():
        try:
            close, states, ma13, ma52, entry = prep(wk)
        except Exception:
            continue
        base = simulate(close, states, ma13, ma52, entry, "HOLD")
        if base is None:
            continue
        rec = {"ticker": t, "theme": theme_of[t],
               "group": "etf" if theme_of[t] == "etf" else "stock",
               "hold_terminal": round(base["terminal"], 3),
               "hold_maxdd": round(base["maxdd"] * 100, 1)}
        for rule in RULES[1:]:
            s = simulate(close, states, ma13, ma52, entry, rule)
            rec[f"{rule}_ratio"] = round(s["terminal"] / base["terminal"], 3)
            rec[f"{rule}_maxdd"] = round(s["maxdd"] * 100, 1)
            rec[f"{rule}_trades"] = s["trades"]
            rec[f"{rule}_pctin"] = s["pct_invested"]
        per_name.append(rec)

    def agg(vals):
        v = sorted(x for x in vals if x is not None)
        if not v:
            return None
        n = len(v)
        return {"n": n, "median": round(v[n // 2], 2),
                "mean": round(sum(v) / n, 2),
                "pct_gt_1": round(sum(1 for x in v if x > 1) / n * 100, 1)}

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "note": "ratio = exit-strategy terminal wealth / hold terminal "
                       "wealth per name; cash yields 0 (anti-exit bias)"}
    for grp in ("stock", "etf"):
        sub = [r for r in per_name if r["group"] == grp]
        g = {"names": len(sub),
             "hold_maxdd_median": agg([r["hold_maxdd"] for r in sub])}
        for rule in RULES[1:]:
            g[rule] = {
                "wealth_ratio": agg([r[f"{rule}_ratio"] for r in sub]),
                "maxdd_median": agg([r[f"{rule}_maxdd"] for r in sub]),
                "dd_improvement_median": round(
                    sorted(r[f"{rule}_maxdd"] - r["hold_maxdd"]
                           for r in sub)[len(sub) // 2], 1) if sub else None,
                "trades_median": sorted(
                    r[f"{rule}_trades"] for r in sub)[len(sub) // 2]
                if sub else None,
                "pct_invested_median": sorted(
                    r[f"{rule}_pctin"] for r in sub)[len(sub) // 2]
                if sub else None,
            }
        results[grp] = g

    (HERE / "exit_results.json").write_text(json.dumps(results, indent=1))
    with open(HERE / "exit_per_name.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_name[0].keys()))
        w.writeheader()
        w.writerows(per_name)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
