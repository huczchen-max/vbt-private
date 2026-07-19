"""Phase 4a — nightly IV snapshot logger (VBT-2; Eric 2026-07-19).

There is no free historical implied-volatility source, so we build our
own: every weekday night, snapshot the option chains of the benchmark
ETFs + the winner screen's top-5 per theme and log ATM IV (~30d and
~60d), a put-skew proxy, and 20d realized vol. In ~3 months this becomes
a usable IV-rank database — the second axis (after direction/regime) of
the options strategy grid.

Appends to iv_history.csv (private). Fails soft everywhere: a missing
chain logs nothing for that symbol and never breaks the pipeline.
"""
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
ETFS = ["SPY", "QQQ", "SMH", "GRID", "BOTZ", "ITA", "XLV"]
TOP_N = 5


def universe():
    syms = list(ETFS)
    try:
        w = json.loads((HERE / "winners.json").read_text())
        for ranked in w.get("themes", {}).values():
            for r in ranked[:TOP_N]:
                if r["ticker"] not in syms:
                    syms.append(r["ticker"])
    except Exception as e:
        print(f"WARN winners.json unavailable: {e}", file=sys.stderr)
    return syms


def atm_iv(tk, spot, exp):
    """Average IV of the call+put nearest the spot for one expiration,
    plus a put-skew proxy (IV of ~10% OTM put minus ATM IV)."""
    ch = tk.option_chain(exp)
    out = {}
    for side, df in (("call", ch.calls), ("put", ch.puts)):
        df = df.dropna(subset=["impliedVolatility"])
        df = df[df["impliedVolatility"] > 0.01]
        if df.empty:
            continue
        row = df.iloc[(df["strike"] - spot).abs().argsort()[:1]]
        out[side] = float(row["impliedVolatility"].iloc[0])
        if side == "put":
            otm = df.iloc[(df["strike"] - spot * 0.9).abs().argsort()[:1]]
            out["put_otm10"] = float(otm["impliedVolatility"].iloc[0])
    if not out:
        return None
    ivs = [v for k, v in out.items() if k in ("call", "put")]
    atm = sum(ivs) / len(ivs)
    skew = out.get("put_otm10", atm) - atm
    return {"atm_iv": atm, "put_skew": skew}


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    syms = universe()
    rows = []
    for t in syms:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="3mo", interval="1d", auto_adjust=True)
            if hist.empty:
                continue
            spot = float(hist["Close"].iloc[-1])
            rets = hist["Close"].pct_change().dropna().tail(20)
            rv20 = float(rets.std() * math.sqrt(252)) if len(rets) >= 15 else None
            exps = tk.options
            if not exps:
                continue
            now = pd.Timestamp.now(tz="UTC").tz_localize(None)
            with_dte = [(e, (pd.Timestamp(e) - now).days) for e in exps]
            pick30 = min(with_dte, key=lambda x: abs(x[1] - 30))
            pick60 = min(with_dte, key=lambda x: abs(x[1] - 60))
            iv30 = atm_iv(tk, spot, pick30[0])
            iv60 = atm_iv(tk, spot, pick60[0]) if pick60[0] != pick30[0] else None
            if not iv30:
                continue
            rows.append({
                "date": today, "ticker": t, "spot": round(spot, 2),
                "dte30": pick30[1],
                "iv30": round(iv30["atm_iv"], 4),
                "put_skew30": round(iv30["put_skew"], 4),
                "dte60": pick60[1] if iv60 else None,
                "iv60": round(iv60["atm_iv"], 4) if iv60 else None,
                "rv20": round(rv20, 4) if rv20 else None,
                "iv_rv_spread": round(iv30["atm_iv"] - rv20, 4) if rv20 else None,
            })
        except Exception as e:
            print(f"WARN iv {t}: {e}", file=sys.stderr)
        time.sleep(0.5)
    if not rows:
        print("iv_log: no rows captured")
        return
    logp = HERE / "iv_history.csv"
    new = not logp.exists()
    fields = ["date", "ticker", "spot", "dte30", "iv30", "put_skew30",
              "dte60", "iv60", "rv20", "iv_rv_spread"]
    with open(logp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"iv_log: {len(rows)}/{len(syms)} symbols logged for {today}")
    for r in rows[:8]:
        print(f"  {r['ticker']:5s} iv30 {r['iv30']:.0%}  rv20 "
              f"{r['rv20'] if r['rv20'] is None else format(r['rv20'], '.0%')}  "
              f"skew {r['put_skew30']:+.1%}")


if __name__ == "__main__":
    main()
