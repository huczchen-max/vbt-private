"""Phase 2 winner screen — quantitative ranking within each theme
(VBT-2; Eric 2026-07-19).

Per non-ETF name in thesis_universe.csv:
  GROWTH     — latest quarterly revenue YoY growth
  ACCEL      — change in YoY growth vs the prior quarter (acceleration)
  MARGINFLECT— latest operating margin minus avg of prior 3 quarters
  RS26 / RS13— 26w/13w return minus the THEME ETF's return
  TREND      — L1 intact (13w MA > 52w MA), weekly structure state,
               fresh confirmed bottom within 13 weeks (radar logic)

Composite: within-theme percentile ranks, weighted
  growth .20  accel .15  margin .15  rs26 .20  rs13 .10  + trend bonus
  (+.10 intact, +.06 Uptrend, +.04 fresh bottom) -> score 0-100.

Outputs: winners.json (ranked per theme), winners_log.csv (append —
forward-logged so the ranking itself becomes scoreable).
Weekly via winners.yml (Saturdays, after the radar).
"""
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from breakout_radar import causal_trend_history, analyze  # noqa: E402

BENCH = {"ai": "SMH", "grid": "GRID", "robotics": "BOTZ",
         "defense": "ITA", "health": "XLV", "outlier": "QQQ"}
WEIGHTS = {"growth": .20, "accel": .15, "margin": .15, "rs26": .20, "rs13": .10}
CHUNK = 100


def quarterly_fundamentals(t):
    """Revenue YoY growth, acceleration, margin inflection from quarterly
    statements. Returns dict of raw values (None where unavailable)."""
    out = {"growth": None, "accel": None, "margin": None}
    try:
        q = yf.Ticker(t).quarterly_income_stmt
        if q is None or q.empty:
            return out
        cols = sorted(q.columns, reverse=True)

        def row(name):
            return q.loc[name] if name in q.index else None
        rev, op = row("Total Revenue"), row("Operating Income")
        if rev is not None and len(cols) >= 5:
            r0, r4 = rev.get(cols[0]), rev.get(cols[4])
            if pd.notna(r0) and pd.notna(r4) and r4:
                out["growth"] = float(r0) / float(r4) - 1
            if len(cols) >= 6:
                r1, r5 = rev.get(cols[1]), rev.get(cols[5])
                if (out["growth"] is not None and pd.notna(r1)
                        and pd.notna(r5) and r5):
                    out["accel"] = out["growth"] - (float(r1) / float(r5) - 1)
        if rev is not None and op is not None and len(cols) >= 4:
            ms = []
            for c in cols[:4]:
                r, o = rev.get(c), op.get(c)
                if pd.notna(r) and pd.notna(o) and r:
                    ms.append(float(o) / float(r))
            if len(ms) >= 3:
                out["margin"] = ms[0] - sum(ms[1:]) / len(ms[1:])
    except Exception as e:
        print(f"WARN fundamentals {t}: {e}", file=sys.stderr)
    return out


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    names = [(r["ticker"], r["theme"]) for r in rows if r["theme"] != "etf"]
    today = datetime.now(timezone.utc).date().isoformat()

    bench_px = {}
    for b in sorted(set(BENCH.values())):
        d = yf.download(b, period="2y", interval="1wk",
                        progress=False, auto_adjust=True)
        bench_px[b] = d["Close"].squeeze()

    recs = {}
    tl = [t for t, _ in names]
    for i in range(0, len(tl), CHUNK):
        batch = tl[i:i + CHUNK]
        df = yf.download(batch, period="2y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                wk = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(wk) < 60:
                    continue
                close = wk["Close"]
                ma13 = close.rolling(13).mean()
                ma52 = close.rolling(52).mean()
                r = analyze(wk) or {}
                recs[t] = {
                    "close": float(close.iloc[-1]),
                    "ret26": float(close.iloc[-1]) / float(close.iloc[-27]) - 1
                    if len(close) > 27 else None,
                    "ret13": float(close.iloc[-1]) / float(close.iloc[-14]) - 1
                    if len(close) > 14 else None,
                    "intact": bool(pd.notna(ma52.iloc[-1])
                                   and float(ma13.iloc[-1]) > float(ma52.iloc[-1])),
                    "state": r.get("state"),
                    "bottom_recent": bool(r.get("bottom")),
                    "dd_pct": r.get("dd_pct"),
                }
            except Exception:
                continue
        print(f"prices {min(i + CHUNK, len(tl))}/{len(tl)}", flush=True)

    theme_of = dict(names)
    for t in list(recs):
        time.sleep(0.4)
        recs[t].update(quarterly_fundamentals(t))
        b = bench_px[BENCH[theme_of[t]]]
        for k, n in (("rs26", 27), ("rs13", 14)):
            rk = recs[t].get(f"ret{n - 1}")
            try:
                br = float(b.iloc[-1]) / float(b.iloc[-n]) - 1
                recs[t][k] = rk - br if rk is not None else None
            except Exception:
                recs[t][k] = None

    # within-theme percentile ranks -> composite
    themes = {}
    for t, r in recs.items():
        themes.setdefault(theme_of[t], []).append(t)
    out_themes = {}
    log_rows = []
    for theme, ts in themes.items():
        def pct(key):
            vals = {t: recs[t].get(key) for t in ts}
            known = sorted((v, t) for t, v in vals.items() if v is not None)
            n = len(known)
            pr = {t: (i + 0.5) / n for i, (_, t) in enumerate(known)}
            return {t: pr.get(t, 0.5) for t in ts}  # missing = neutral
        p = {k: pct(k) for k in WEIGHTS}
        ranked = []
        for t in ts:
            base = sum(WEIGHTS[k] * p[k][t] for k in WEIGHTS) / sum(WEIGHTS.values())
            bonus = ((0.10 if recs[t]["intact"] else 0)
                     + (0.06 if recs[t].get("state") == "Uptrend" else 0)
                     + (0.04 if recs[t].get("bottom_recent") else 0))
            score = round(min(1.0, base * 0.8 + bonus) * 100, 1)
            row = {"ticker": t, "score": score,
                   "growth_pct": round(recs[t]["growth"] * 100, 1)
                   if recs[t].get("growth") is not None else None,
                   "accel_pp": round(recs[t]["accel"] * 100, 1)
                   if recs[t].get("accel") is not None else None,
                   "margin_pp": round(recs[t]["margin"] * 100, 1)
                   if recs[t].get("margin") is not None else None,
                   "rs26_pct": round(recs[t]["rs26"] * 100, 1)
                   if recs[t].get("rs26") is not None else None,
                   "rs13_pct": round(recs[t]["rs13"] * 100, 1)
                   if recs[t].get("rs13") is not None else None,
                   "intact": recs[t]["intact"], "state": recs[t].get("state"),
                   "bottom_recent": recs[t]["bottom_recent"],
                   "dd_pct": recs[t].get("dd_pct")}
            ranked.append(row)
            log_rows.append({"date": today, "theme": theme, **row})
        ranked.sort(key=lambda r: -r["score"])
        out_themes[theme] = ranked

    (HERE / "winners.json").write_text(json.dumps(
        {"date": today, "weights": WEIGHTS, "themes": out_themes}, indent=1))
    logp = HERE / "winners_log.csv"
    new = not logp.exists()
    fields = ["date", "theme", "ticker", "score", "growth_pct", "accel_pp",
              "margin_pp", "rs26_pct", "rs13_pct", "intact", "state",
              "bottom_recent", "dd_pct"]
    with open(logp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(log_rows)
    for theme, ranked in out_themes.items():
        top = ", ".join(f"{r['ticker']}:{r['score']}" for r in ranked[:5])
        print(f"{theme:9s} top5: {top}")


if __name__ == "__main__":
    main()
