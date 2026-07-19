"""Phase 4d — collar vs brake vs hold (VBT-2; Eric 2026-07-19).

The exit study showed selling on breakdowns destroys wealth on single
names, and the COMBO brake is costless only on ETFs. The collar is the
protective idea it left standing: never sell — when the trend BREAKS,
wrap shares in a zero-cost collar (long ~5% OTM put financed by a short
call), roll ~quarterly while broken, lift when the trend repairs.

Strategies per name (10y weekly; enter at first L1 door: fresh 13/52w
MA cross or confirmed deep-correction bottom):
  HOLD    — never exit (the champion to beat).
  BRAKE   — COMBO exit (weekly Downtrend AND close<MA52), re-enter via
            L1 doors (from the exit study).
  COLLAR  — hold always; on intact->broken transition, apply a
            13-week zero-cost collar: put at 95% of spot, call strike
            solved so call premium = put premium (Black-Scholes,
            sigma = 26w realized vol x1.1, r=3%). At expiry, the
            period return is clamped to [K_put/S0, K_call/S0]; roll
            while broken; remove on repair.
APPROXIMATION NOTICE: BS on RV+10% is a stand-in for real chains —
identical across names, so the COMPARISON is meaningful even where
absolute levels are not. Skew (puts cost more than symmetric BS) makes
real zero-cost collars slightly worse than modeled — bias FAVORS the
collar, remember it when reading results.

Metrics: terminal wealth ratio vs HOLD, equity max drawdown, % weeks
collared/invested. Groups: ETF (low survivorship, headline) vs stocks.
Outputs: collar_results.json, collar_per_name.csv (private).
"""
import csv
import json
import math
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
COLLAR_WEEKS = 13
PUT_K = 0.95
R = 0.03


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, sigma, kind):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if kind == "c" else (K - S))
    d1 = (math.log(S / K) + (R + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "c":
        return S * _ncdf(d1) - K * math.exp(-R * T) * _ncdf(d2)
    return K * math.exp(-R * T) * _ncdf(-d2) - S * _ncdf(-d1)


def zero_cost_call_strike(S, T, sigma):
    """Call strike whose premium matches the 95% put's premium."""
    target = bs(S, S * PUT_K, T, sigma, "p")
    best_k, best_diff = S * 1.05, 1e9
    k = S * 1.001
    while k <= S * 1.40:
        diff = abs(bs(S, k, T, sigma, "c") - target)
        if diff < best_diff:
            best_k, best_diff = k, diff
        k *= 1.005
    return best_k


def prep(wk):
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    intact = (ma13 > ma52) & ma52.notna()
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd26 = dd.rolling(26, min_periods=1).min()
    rv = close.pct_change().rolling(26).std() * math.sqrt(52)
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
    return close, states, ma52, intact, rv, entry


def maxdd(curve):
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def simulate(close, states, ma52, intact, rv, entry, mode):
    idxs = [i for i, e in enumerate(entry) if e]
    if not idxs:
        return None
    start = idxs[0]
    eq = [1.0]
    invested = True
    collar = None  # (S0, k_put, k_call, expiry_j, eq_at_entry)
    weeks_col = weeks_in = 0
    for j in range(start + 1, len(close)):
        px, prev = float(close.iloc[j]), float(close.iloc[j - 1])
        broken = not bool(intact.iloc[j])
        if mode == "BRAKE":
            if invested:
                eq.append(eq[-1] * px / prev)
                weeks_in += 1
                if str(states.iloc[j]) == "Downtrend" and \
                        pd.notna(ma52.iloc[j]) and px < float(ma52.iloc[j]):
                    invested = False
            else:
                eq.append(eq[-1])
                if bool(entry.iloc[j]):
                    invested = True
            continue
        # HOLD and COLLAR are always in shares
        eq.append(eq[-1] * px / prev)
        weeks_in += 1
        if mode != "COLLAR":
            continue

        def collar_value(S, c, j_):
            """Weekly mark-to-market of shares + long put - short call."""
            S0, kp, kc, expj, eq0, sig = c
            T = max(0.0, (expj - j_) / 52)
            val = S + bs(S, kp, T, sig, "p") - bs(S, kc, T, sig, "c")
            return eq0 * val / S0

        if collar:
            weeks_col += 1
            eq[-1] = collar_value(px, collar, j)
            expired = j >= collar[3]
            if expired or not broken:
                # settle at expiry, or lift when the trend repairs
                base_eq = eq[-1]
                collar = None
                if expired and broken:  # roll while still broken
                    sig = max(0.15, float(rv.iloc[j]) * 1.1) \
                        if pd.notna(rv.iloc[j]) else 0.4
                    kc2 = zero_cost_call_strike(px, COLLAR_WEEKS / 52, sig)
                    collar = (px, px * PUT_K, kc2, j + COLLAR_WEEKS,
                              base_eq, sig)
        elif broken and bool(intact.iloc[j - 1]):
            # fresh break this week: put the collar on
            sig = max(0.15, float(rv.iloc[j]) * 1.1) \
                if pd.notna(rv.iloc[j]) else 0.4
            kc2 = zero_cost_call_strike(px, COLLAR_WEEKS / 52, sig)
            collar = (px, px * PUT_K, kc2, j + COLLAR_WEEKS, eq[-1], sig)
    n = len(eq)
    return {"terminal": eq[-1], "maxdd": maxdd(eq),
            "pct_in": round(weeks_in / max(1, n - 1) * 100, 1),
            "pct_collared": round(weeks_col / max(1, n - 1) * 100, 1)}


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
            close, states, ma52, intact, rv, entry = prep(wk)
        except Exception as e:
            print(f"WARN {t}: {e}", file=sys.stderr)
            continue
        base = simulate(close, states, ma52, intact, rv, entry, "HOLD")
        if base is None:
            continue
        rec = {"ticker": t, "group": "etf" if theme_of[t] == "etf" else "stock",
               "hold_terminal": round(base["terminal"], 3),
               "hold_maxdd": round(base["maxdd"] * 100, 1)}
        for mode in ("BRAKE", "COLLAR"):
            s = simulate(close, states, ma52, intact, rv, entry, mode)
            rec[f"{mode}_ratio"] = round(s["terminal"] / base["terminal"], 3)
            rec[f"{mode}_maxdd"] = round(s["maxdd"] * 100, 1)
            rec[f"{mode}_pct_collared"] = s["pct_collared"]
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
               "note": "collar priced with BS on RV*1.1 — approximation; "
                       "real skew makes collars slightly worse than modeled"}
    for grp in ("etf", "stock"):
        sub = [r for r in per_name if r["group"] == grp]
        g = {"names": len(sub),
             "hold_maxdd_median": agg([r["hold_maxdd"] for r in sub])}
        for mode in ("BRAKE", "COLLAR"):
            g[mode] = {
                "wealth_ratio": agg([r[f"{mode}_ratio"] for r in sub]),
                "maxdd_median": agg([r[f"{mode}_maxdd"] for r in sub]),
                "dd_improvement_median": round(sorted(
                    r[f"{mode}_maxdd"] - r["hold_maxdd"]
                    for r in sub)[len(sub) // 2], 1) if sub else None,
                "pct_collared_median": sorted(
                    r[f"{mode}_pct_collared"] for r in sub)[len(sub) // 2]
                if sub else None,
            }
        results[grp] = g
    (HERE / "collar_results.json").write_text(json.dumps(results, indent=1))
    with open(HERE / "collar_per_name.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_name[0].keys()))
        w.writeheader()
        w.writerows(per_name)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
