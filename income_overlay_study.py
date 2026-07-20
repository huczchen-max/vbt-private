"""Income-overlay study — does systematic put-selling BENEATH a
long-term winner add return after paying its losses in corrections?
(VBT-2 'one winner' thesis; Eric 2026-07-19.)

Per name (10y weekly, from first L1 door — same frame as every study):
  HOLD    — 100 shares, untouched.
  OVERLAY — same 100 shares + a rolling bull put spread (1 contract =
            100-share equivalent, i.e. FULL coverage; scale linearly
            for a 20%-sleeve version): sell 6-week spread, short K =
            90% of spot, long K = 85%, priced Black-Scholes at
            sigma = 26w RV x 1.1; weekly BS mark-to-market;
            close at 60% of credit / on breach (spot < short K) /
            at expiry; reopen when gates pass.
  GATES (doctrine): trend intact (13w>52w MA) AND weekly structure not
  Downtrend AND not parabolic (weekly ext over 40w MA in top decile of
  own expanding history). Earnings blackout is NOT modeled (real engine
  has it) — overlay results optimistic on that axis; BS-without-skew
  understates real put credits — pessimistic on that axis. Noted.

Accounting: overlay income accumulates as cash (no reinvest — the
conservative choice). Report annualized income yield on average core
value, worst cycle loss, cycle win rate, and terminal HOLD vs
HOLD+OVERLAY. Names split by 10y multiple: WINNER >=4x / MID 1.5-4x /
LAGGARD <1.5x — the thesis question is whether the overlay is safe
specifically on WINNERS.

Outputs: overlay_results.json, overlay_per_name.csv (private).
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
from breakout_radar import causal_trend_history  # noqa: E402

CHUNK = 100
SPREAD_WEEKS = 6
SHORT_K = 0.90
LONG_K = 0.85
PROFIT_TAKE = 0.60
R = 0.03


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_put(S, K, T, sigma):
    if T <= 0 or sigma <= 0:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (R + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-R * T) * _ncdf(-d2) - S * _ncdf(-d1)


def spread_value(S, ks, kl, T, sigma):
    return bs_put(S, ks, T, sigma) - bs_put(S, kl, T, sigma)


def prep(wk):
    close, high, low = wk["Close"], wk["High"], wk["Low"]
    states = causal_trend_history(high, low)
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    ma40 = close.rolling(40).mean()
    intact = (ma13 > ma52) & ma52.notna()
    rv = close.pct_change().rolling(26).std() * math.sqrt(52)
    ext = close / ma40 - 1
    # expanding-percentile parabolic flag (causal)
    para = []
    hist = []
    for v in ext:
        p = False
        if pd.notna(v):
            if len(hist) >= 100:
                p = (sum(1 for x in hist if x < v) / len(hist)) >= 0.90 and v > 0
            hist.append(float(v))
        para.append(p)
    para = pd.Series(para, index=wk.index)
    # first L1 door (MACROSS or BOTTOM) — reuse minimal version
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd26 = dd.rolling(26, min_periods=1).min()
    start = None
    for j in range(56, len(wk)):
        mac = (pd.notna(ma52.iloc[j]) and pd.notna(ma52.iloc[j - 1])
               and float(ma13.iloc[j]) > float(ma52.iloc[j])
               and float(ma13.iloc[j - 1]) <= float(ma52.iloc[j - 1]))
        bot = (str(states.iloc[j]) == "Uptrend"
               and str(states.iloc[j - 1]) != "Uptrend"
               and float(dd.iloc[j]) <= -0.15 and float(dd26.iloc[j]) <= -0.30)
        if mac or bot:
            start = j
            break
    return close, states, intact, rv, para, start


def simulate(close, states, intact, rv, para, start):
    """Returns overlay cash stream stats (per 100-share core)."""
    cash = 0.0
    spread = None  # (ks, kl, credit, exp_j, sigma)
    cycles = wins = 0
    worst = 0.0
    yearly = {}
    core_vals = []
    for j in range(start, len(close)):
        S = float(close.iloc[j])
        core_vals.append(S * 100)
        yr = close.index[j].year
        gates = (bool(intact.iloc[j])
                 and str(states.iloc[j]) != "Downtrend"
                 and not bool(para.iloc[j]))
        sig = max(0.15, float(rv.iloc[j]) * 1.1) if pd.notna(rv.iloc[j]) else 0.4
        if spread:
            ks, kl, credit, expj, s0 = spread
            T = max(0.0, (expj - j) / 52)
            mark = spread_value(S, ks, kl, T, s0)
            done = pnl = None
            if j >= expj:
                pnl = (credit - min(max(ks - S, 0.0), ks - kl)) * 100
                done = "expiry"
            elif mark <= credit * (1 - PROFIT_TAKE):
                pnl = (credit - mark) * 100
                done = "profit"
            elif S < ks:
                pnl = (credit - mark) * 100
                done = "breach"
            if done:
                cash += pnl
                yearly[yr] = yearly.get(yr, 0) + pnl
                cycles += 1
                wins += 1 if pnl > 0 else 0
                worst = min(worst, pnl)
                spread = None
        if spread is None and gates:
            ks, kl = S * SHORT_K, S * LONG_K
            credit = spread_value(S, ks, kl, SPREAD_WEEKS / 52, sig)
            if credit > 0.05 * (ks - kl):
                spread = (ks, kl, credit, j + SPREAD_WEEKS, sig)
    avg_core = sum(core_vals) / len(core_vals) if core_vals else 1
    yrs = max(1e-9, len(core_vals) / 52)
    return {"income_total": round(cash, 0),
            "income_yield_pct": round(cash / yrs / avg_core * 100, 2),
            "cycles": cycles,
            "cycle_win_pct": round(100 * wins / cycles, 1) if cycles else None,
            "worst_cycle": round(worst, 0),
            "yearly_min": round(min(yearly.values()), 0) if yearly else 0}


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    tickers = [r["ticker"] for r in rows if r["theme"] != "etf"]
    data = {}
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        df = yf.download(batch, period="10y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(sub) >= 150:
                    data[t] = sub
            except Exception:
                continue
        print(f"downloaded {min(i + CHUNK, len(tickers))}/{len(tickers)}",
              flush=True)

    per_name = []
    for t, wk in data.items():
        try:
            close, states, intact, rv, para, start = prep(wk)
            if start is None or len(close) - start < 104:
                continue
            mult = float(close.iloc[-1]) / float(close.iloc[start])
            tier = ("WINNER" if mult >= 4 else
                    "MID" if mult >= 1.5 else "LAGGARD")
            ov = simulate(close, states, intact, rv, para, start)
            hold_pnl = (float(close.iloc[-1]) - float(close.iloc[start])) * 100
            per_name.append({"ticker": t, "tier": tier,
                             "multiple": round(mult, 2),
                             "hold_pnl": round(hold_pnl, 0), **ov,
                             "overlay_vs_hold_pct": round(
                                 100 * ov["income_total"] / abs(hold_pnl), 1)
                             if hold_pnl else None})
        except Exception as e:
            print(f"WARN {t}: {e}", file=sys.stderr)

    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return round(v[len(v) // 2], 2) if v else None

    results = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "biases": "no earnings blackout modeled (optimistic); "
                         "BS w/o skew understates real put credits "
                         "(pessimistic); income held as cash, not "
                         "reinvested (conservative)"}
    for tier in ("WINNER", "MID", "LAGGARD"):
        sub = [r for r in per_name if r["tier"] == tier]
        results[tier] = {
            "names": len(sub),
            "income_yield_pct_median": med([r["income_yield_pct"] for r in sub]),
            "pct_names_income_positive": round(
                100 * sum(1 for r in sub if r["income_total"] > 0)
                / len(sub), 1) if sub else None,
            "cycle_win_pct_median": med([r["cycle_win_pct"] for r in sub]),
            "worst_cycle_median": med([r["worst_cycle"] for r in sub]),
            "worst_year_median": med([r["yearly_min"] for r in sub]),
            "overlay_income_vs_hold_pnl_pct_median": med(
                [r["overlay_vs_hold_pct"] for r in sub]),
        }
    (HERE / "overlay_results.json").write_text(json.dumps(results, indent=1))
    with open(HERE / "overlay_per_name.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_name[0].keys()))
        w.writeheader()
        w.writerows(per_name)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
